package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"time"
)

type Config struct {
	AmpURL               string `json:"amp_url"`
	AmpUsername          string `json:"amp_username"`
	AmpPassword          string `json:"amp_password"`
	BindAddress          string `json:"bind_address"`
	CacheDurationSeconds int    `json:"cache_duration_seconds"`
}

type LoginRequest struct {
	Username   string `json:"username"`
	Password   string `json:"password"`
	Token      string `json:"token"`
	RememberMe bool   `json:"rememberMe"`
}

type LoginResponse struct {
	SessionID string `json:"sessionID"`
	Success   bool   `json:"success"`
}

type Instance struct {
	InstanceID   string `json:"InstanceID"`
	InstanceName string `json:"InstanceName"`
	FriendlyName string `json:"FriendlyName"`
	Module       string `json:"Module"`
	Running      bool   `json:"Running"`
	URL          string `json:"URL"`
}

type Target struct {
	TargetName         string     `json:"TargetName"`
	AvailableInstances []Instance `json:"AvailableInstances"`
}

type PublicServerInfo struct {
	Name    string `json:"name"`
	Module  string `json:"module"`
	Running bool   `json:"running"`
}

type BridgeService struct {
	config Config
	
	mu          sync.Mutex
	sessionID   string
	cachedStats []PublicServerInfo
	lastCache   time.Time
}

func main() {
	var configPath string
	flag.StringVar(&configPath, "config", "", "Path to configuration JSON file")
	flag.Parse()

	// Locate config file
	if configPath == "" {
		// 1. Try /etc/antigravity-amp/config.json
		p := "/etc/antigravity-amp/config.json"
		if _, err := os.Stat(p); err == nil {
			configPath = p
		} else {
			// 2. Try relative path config.json
			configPath = "config.json"
		}
	}

	log.Printf("Starting AMP Status Bridge. Loading config from: %s", configPath)
	cfg, err := loadConfig(configPath)
	if err != nil {
		log.Fatalf("Error loading config: %v. Please make sure config file exists and is valid JSON.", err)
	}

	if cfg.BindAddress == "" {
		cfg.BindAddress = "0.0.0.0:9876"
	}
	if cfg.CacheDurationSeconds <= 0 {
		cfg.CacheDurationSeconds = 10
	}

	bridge := &BridgeService{
		config: cfg,
	}

	http.HandleFunc("/api/status", bridge.handleStatus)

	log.Printf("Listening on http://%s", cfg.BindAddress)
	if err := http.ListenAndServe(cfg.BindAddress, nil); err != nil {
		log.Fatalf("Server failed to bind or run: %v", err)
	}
}

func loadConfig(path string) (Config, error) {
	file, err := os.Open(path)
	if err != nil {
		return Config{}, err
	}
	defer file.Close()

	var cfg Config
	decoder := json.NewDecoder(file)
	if err := decoder.Decode(&cfg); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func (b *BridgeService) login() error {
	loginPayload := LoginRequest{
		Username:   b.config.AmpUsername,
		Password:   b.config.AmpPassword,
		Token:      "",
		RememberMe: false,
	}

	payloadBytes, err := json.Marshal(loginPayload)
	if err != nil {
		return err
	}

	url := fmt.Sprintf("%s/API/Core/Login", b.config.AmpURL)
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(payloadBytes))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("login failed with status %d: %s", resp.StatusCode, string(respBytes))
	}

	var loginResp LoginResponse
	if err := json.Unmarshal(respBytes, &loginResp); err != nil {
		// Try fallback for alternate capitalizations like SessionID
		type LoginFallback struct {
			SessionID string `json:"SessionID"`
		}
		var fb LoginFallback
		if errFB := json.Unmarshal(respBytes, &fb); errFB == nil && fb.SessionID != "" {
			b.sessionID = fb.SessionID
			return nil
		}
		return fmt.Errorf("failed to parse login response: %w", err)
	}

	if loginResp.SessionID == "" {
		return fmt.Errorf("login response did not contain a sessionID: %s", string(respBytes))
	}

	b.sessionID = loginResp.SessionID
	log.Printf("Successfully authenticated with AMP API. New SessionID starts with %s...", b.sessionID[:8])
	return nil
}

func (b *BridgeService) getInstances() ([]Target, error) {
	if b.sessionID == "" {
		if err := b.login(); err != nil {
			return nil, err
		}
	}

	targets, err := b.fetchInstancesRequest()
	if err != nil {
		log.Printf("GetInstances request failed: %v. Retrying login...", err)
		// Force re-login and attempt query once more
		if loginErr := b.login(); loginErr != nil {
			return nil, fmt.Errorf("re-auth failed: %w", loginErr)
		}
		return b.fetchInstancesRequest()
	}

	return targets, nil
}

func (b *BridgeService) fetchInstancesRequest() ([]Target, error) {
	url := fmt.Sprintf("%s/API/ADSModule/GetInstances", b.config.AmpURL)
	
	// Pass SESSIONID inside JSON body for older AMP implementations
	bodyData := map[string]string{
		"SESSIONID": b.sessionID,
	}
	bodyBytes, err := json.Marshal(bodyData)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(bodyBytes))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	// Pass session ID as Bearer token for newer implementations
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", b.sessionID))

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(respBytes))
	}

	// Inspect if AMP returned an error envelope
	type AmpError struct {
		Message string `json:"Message"`
		Error   int    `json:"Error"`
	}
	var ampErr AmpError
	if err := json.Unmarshal(respBytes, &ampErr); err == nil && (ampErr.Error != 0 || ampErr.Message != "") {
		return nil, fmt.Errorf("AMP API error: %s (code %d)", ampErr.Message, ampErr.Error)
	}

	return parseInstances(respBytes)
}

func parseInstances(body []byte) ([]Target, error) {
	// 1. Try parsing as a raw array of Targets
	var rawList []Target
	if err := json.Unmarshal(body, &rawList); err == nil {
		return rawList, nil
	}

	// 2. Try parsing as JSON-RPC Result object {"Result": []Target}
	type AmpEnvelope struct {
		Result []Target `json:"Result"`
	}
	var env AmpEnvelope
	if err := json.Unmarshal(body, &env); err == nil && len(env.Result) > 0 {
		return env.Result, nil
	}

	// 3. Try parsing as lowercase result {"result": []Target}
	type AmpEnvelopeLower struct {
		Result []Target `json:"result"`
	}
	var envLower AmpEnvelopeLower
	if err := json.Unmarshal(body, &envLower); err == nil && len(envLower.Result) > 0 {
		return envLower.Result, nil
	}

	return nil, fmt.Errorf("unable to parse instances response: %s", string(body))
}

func (b *BridgeService) handleStatus(w http.ResponseWriter, r *http.Request) {
	// Add broad CORS configuration to enable cross-domain access from websites
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

	if r.Method == "OPTIONS" {
		w.WriteHeader(http.StatusOK)
		return
	}

	if r.Method != "GET" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	b.mu.Lock()
	defer b.mu.Unlock()

	// Check if cached stats exist and are still fresh
	cacheAge := time.Since(b.lastCache)
	cacheDuration := time.Duration(b.config.CacheDurationSeconds) * time.Second

	if len(b.cachedStats) == 0 || cacheAge > cacheDuration {
		log.Println("Querying AMP backend for latest instance statuses...")
		targets, err := b.getInstances()
		if err != nil {
			log.Printf("AMP query failed: %v", err)
			// Return stale cached data if we have it, otherwise error
			if len(b.cachedStats) > 0 {
				log.Println("Serving stale cached server status due to query failure.")
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(b.cachedStats)
				return
			}
			http.Error(w, fmt.Sprintf("Error querying AMP: %v", err), http.StatusInternalServerError)
			return
		}

		var publicList []PublicServerInfo
		for _, target := range targets {
			for _, inst := range target.AvailableInstances {
				name := inst.FriendlyName
				if name == "" {
					name = inst.InstanceName
				}
				// Filter to only return safe public status fields
				publicList = append(publicList, PublicServerInfo{
					Name:    name,
					Module:  inst.Module,
					Running: inst.Running,
				})
			}
		}

		b.cachedStats = publicList
		b.lastCache = time.Now()
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(b.cachedStats); err != nil {
		log.Printf("Failed to encode response: %v", err)
	}
}
