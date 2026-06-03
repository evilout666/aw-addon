# Antigravity AMP Status Bridge

This Go service runs in the background on your Linux server, authenticates with your local CubeCoders AMP (Application Management Panel) ADS instance, and exposes a clean, unauthenticated server status endpoint. 

By querying this service instead of your actual AMP installation, your public web pages can display server statuses (e.g., whether a game server is running or stopped) without exposing sensitive credentials or Session IDs.

---

## 🛠️ Installation & Setup

1. **Clone/Download the repository** containing this directory to your server.
2. **Execute the installation script** as root:
   ```bash
   sudo ./install.sh
   ```
   *The script will automatically detect and install Go (via `apt-get` if missing), compile the binary, create a systemd daemon, and register the service.*

3. **Configure the credentials** by editing the configuration file:
   ```bash
   sudo nano /etc/antigravity-amp/config.json
   ```
   Provide your local AMP URL, admin username, and password:
   ```json
   {
     "amp_url": "http://localhost:8080",
     "amp_username": "admin",
     "amp_password": "yourpasswordhere",
     "bind_address": "0.0.0.0:9876",
     "cache_duration_seconds": 10
   }
   ```

4. **Start the service**:
   ```bash
   sudo systemctl restart antigravity-amp
   ```

5. **Verify the service is running and view logs**:
   ```bash
   sudo systemctl status antigravity-amp
   sudo journalctl -u antigravity-amp -f
   ```

---

## 🔌 API Documentation

### Get Server Statuses

* **Endpoint:** `/api/status`
* **Method:** `GET`
* **CORS Support:** Permitted (`Access-Control-Allow-Origin: *`), making it safe to query from external dashboards.
* **Cache:** Automatic response caching in-memory (default 10s) to prevent overloading the AMP instance with frequent queries.

#### Response Format (JSON Array):
```json
[
  {
    "name": "AFTERWORK Gaming (Minecraft)",
    "module": "Minecraft",
    "running": true
  },
  {
    "name": "Valheim Coop",
    "module": "Valheim",
    "running": false
  }
]
```

---

## 💻 Webpage Integration Example

Use this simple snippet on your dashboard/webpage to fetch and render the live server statuses:

```javascript
async function fetchServerStatuses() {
    try {
        const response = await fetch('http://YOUR_SERVER_IP:9876/api/status');
        const servers = await response.json();
        
        const container = document.getElementById('servers-container');
        container.innerHTML = servers.map(srv => `
            <div class="server-card">
                <h3>${srv.name}</h3>
                <p>Game Type: <strong>${srv.module}</strong></p>
                <span class="status-badge ${srv.running ? 'online' : 'offline'}">
                    ${srv.running ? '🟢 Online' : '🔴 Offline'}
                </span>
            </div>
        `).join('');
    } catch (err) {
        console.error('Failed to query server statuses:', err);
    }
}
```
