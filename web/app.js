// Afterwork Dashboard Controller Logic

document.addEventListener('DOMContentLoaded', () => {
    // --- Centralized DOM Variable Declarations (Avoid TDZ / Reference Errors) ---
    
    // Navigation Elements
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const tabTitle = document.getElementById('tab-title');
    const tabSubtitle = document.getElementById('tab-subtitle');

    // AMP Status Configuration & Control Elements
    const toggleAmpStatus = document.getElementById('toggle-amp-status');
    const ampStatusBtn = document.querySelector('.nav-btn[data-tab="amp-status"]');
    const ampApiUrlInput = document.getElementById('amp-api-url');
    const btnSaveApiUrl = document.getElementById('btn-save-api-url');
    const btnRefreshStatus = document.getElementById('btn-refresh-status');
    const ampLoader = document.getElementById('amp-loader');
    const ampError = document.getElementById('amp-error');
    const ampErrorText = document.getElementById('amp-error-text');
    const serversGrid = document.getElementById('servers-grid');

    // Live Control Elements
    const toggleLiveControl = document.getElementById('toggle-live-control');
    const channelInputGroup = document.getElementById('channel-input-group');
    const channelSelectGroup = document.getElementById('channel-select-group');
    const liveSettingsGroup = document.getElementById('live-settings-group');
    const sendLiveBtn = document.getElementById('send-live-btn');
    const backendApiUrlInput = document.getElementById('backend-api-url');
    const btnSaveBackendUrl = document.getElementById('btn-save-backend-url');
    const btnRefreshChannels = document.getElementById('btn-refresh-channels');
    const embedChannelSelect = document.getElementById('embed-channel-select');
    const backendApiToken = document.getElementById('backend-api-token');
    const ampApiToken = document.getElementById('amp-api-token');

    // Toast Elements
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');

    // Embed Form Inputs
    const embedChannel = document.getElementById('embed-channel');
    const embedTitle = document.getElementById('embed-title');
    const embedDescription = document.getElementById('embed-description');
    const embedColor = document.getElementById('embed-color');
    const embedColorHex = document.getElementById('embed-color-hex');
    const embedThumbnail = document.getElementById('embed-thumbnail');
    const embedImage = document.getElementById('embed-image');
    const addFieldBtn = document.getElementById('add-field-btn');
    const fieldsContainer = document.getElementById('fields-container');

    // Embed Preview Elements
    const previewEmbedBorder = document.getElementById('preview-embed-border');
    const previewTitle = document.getElementById('preview-title');
    const previewDescription = document.getElementById('preview-description');
    const previewFields = document.getElementById('preview-fields');
    const previewThumbnailContainer = document.getElementById('preview-thumbnail-container');
    const previewThumbnail = document.getElementById('preview-thumbnail');
    const previewImageContainer = document.getElementById('preview-image-container');
    const previewImage = document.getElementById('preview-image');

    // Outputs
    const generatedCommand = document.getElementById('generated-command');
    const copyCmdBtn = document.getElementById('copy-cmd-btn');
    const copyJsonBtn = document.getElementById('copy-json-btn');

    // RSS Inputs & Outputs
    const rssName = document.getElementById('rss-name');
    const rssChannel = document.getElementById('rss-channel');
    const rssUrl = document.getElementById('rss-url');
    const rssAddCmd = document.getElementById('rss-add-cmd');
    const rssRemoveCmd = document.getElementById('rss-remove-cmd');
    const copyRssAddBtn = document.getElementById('copy-rss-add-btn');
    const copyRssRemoveBtn = document.getElementById('copy-rss-remove-btn');

    // --- Navigation System ---

    const tabMeta = {
        'embed-builder': {
            title: 'Embed Builder',
            subtitle: 'Design custom rich embeds and generate pasteable bot commands.'
        },
        'rss-manager': {
            title: 'RSS Manager',
            subtitle: 'Configure RSS/Atom feed integrations and copy management commands.'
        },
        'quick-deploy': {
            title: 'Quick Deployer',
            subtitle: 'Copy commands to deploy and set up configuration panels on your server.'
        },
        'amp-status': {
            title: 'AMP Server Status',
            subtitle: 'Live status check and monitoring dashboard for all managed game servers.'
        },
        'documentation': {
            title: 'Documentation',
            subtitle: 'Complete command reference and function manuals for the Afterwork cog.'
        }
    };

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            
            // Toggle active classes on buttons
            navButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Toggle active classes on tab contents
            tabContents.forEach(content => {
                content.classList.remove('active');
                if (content.id === targetTab) {
                    content.classList.add('active');
                }
            });
            
            // Update title & subtitle
            if (tabMeta[targetTab]) {
                tabTitle.textContent = tabMeta[targetTab].title;
                tabSubtitle.textContent = tabMeta[targetTab].subtitle;
            }

            // Automatically query status bridge when opening the AMP tab
            if (targetTab === 'amp-status') {
                fetchAmpStatus();
            }
        });
    });

    // --- AMP Status Tab Toggle Logic ---

    // Initialize state from localStorage (default: hidden)
    const isAmpEnabled = localStorage.getItem('show-amp-status') === 'true';
    toggleAmpStatus.checked = isAmpEnabled;
    ampStatusBtn.style.display = isAmpEnabled ? 'flex' : 'none';

    toggleAmpStatus.addEventListener('change', () => {
        const enabled = toggleAmpStatus.checked;
        localStorage.setItem('show-amp-status', enabled ? 'true' : 'false');
        ampStatusBtn.style.display = enabled ? 'flex' : 'none';

        // If disabling the tab while viewing it, fallback to default embed-builder tab
        if (!enabled && ampStatusBtn.classList.contains('active')) {
            const defaultBtn = document.querySelector('.nav-btn[data-tab="embed-builder"]');
            if (defaultBtn) defaultBtn.click();
        }
    });

    // --- Live Control Mode Toggle Logic ---

    // Load connection settings
    const savedGoBackendUrl = localStorage.getItem('go_backend_url') || 'http://localhost:9876';
    if (backendApiUrlInput) {
        backendApiUrlInput.value = savedGoBackendUrl;
    }
    const savedToken = localStorage.getItem('dashboard_token') || '';
    if (backendApiToken) {
        backendApiToken.value = savedToken;
    }
    if (ampApiToken) {
        ampApiToken.value = savedToken;
    }

    // Initialize toggle state from localStorage (default: false)
    const isLiveEnabled = localStorage.getItem('enable-live-control') === 'true';
    if (toggleLiveControl) {
        toggleLiveControl.checked = isLiveEnabled;
        
        // Show/hide elements on initialization
        if (channelInputGroup) channelInputGroup.style.display = isLiveEnabled ? 'none' : 'block';
        if (channelSelectGroup) channelSelectGroup.style.display = isLiveEnabled ? 'block' : 'none';
        if (liveSettingsGroup) liveSettingsGroup.style.display = isLiveEnabled ? 'block' : 'none';
        if (sendLiveBtn) sendLiveBtn.style.display = isLiveEnabled ? 'inline-flex' : 'none';

        if (isLiveEnabled) {
            fetchBotChannels();
        }

        toggleLiveControl.addEventListener('change', () => {
            const enabled = toggleLiveControl.checked;
            localStorage.setItem('enable-live-control', enabled ? 'true' : 'false');
            
            if (channelInputGroup) channelInputGroup.style.display = enabled ? 'none' : 'block';
            if (channelSelectGroup) channelSelectGroup.style.display = enabled ? 'block' : 'none';
            if (liveSettingsGroup) liveSettingsGroup.style.display = enabled ? 'block' : 'none';
            if (sendLiveBtn) sendLiveBtn.style.display = enabled ? 'inline-flex' : 'none';

            if (enabled) {
                fetchBotChannels();
            } else {
                updateEmbedPreview();
            }
        });
    }

    if (btnSaveBackendUrl && backendApiUrlInput) {
        btnSaveBackendUrl.addEventListener('click', () => {
            let url = backendApiUrlInput.value.trim();
            if (!url) {
                showToast('Please enter a valid URL', true);
                return;
            }
            // Strip any trailing API endpoints to get the base URL
            url = url.replace(/\/api\/status\/?$/, '');
            url = url.replace(/\/api\/bot\/channels\/?$/, '');
            url = url.replace(/\/api\/bot\/embed\/?$/, '');
            if (url.endsWith('/')) {
                url = url.slice(0, -1);
            }
            backendApiUrlInput.value = url;
            localStorage.setItem('go_backend_url', url);
            localStorage.setItem('amp_api_url', `${url}/api/status`);
            if (ampApiUrlInput) {
                ampApiUrlInput.value = `${url}/api/status`;
            }
            const token = (backendApiToken && backendApiToken.value.trim()) || '';
            localStorage.setItem('dashboard_token', token);
            if (ampApiToken) {
                ampApiToken.value = token;
            }
            showToast('Connection settings saved!');
            fetchBotChannels();
        });
    }

    if (btnRefreshChannels) {
        btnRefreshChannels.addEventListener('click', () => {
            fetchBotChannels();
        });
    }

    if (embedChannelSelect) {
        embedChannelSelect.addEventListener('change', updateEmbedPreview);
    }

    async function fetchBotChannels() {
        if (!embedChannelSelect) return;
        
        embedChannelSelect.disabled = true;
        embedChannelSelect.innerHTML = '<option value="">Loading channels...</option>';
        
        const baseUrl = localStorage.getItem('go_backend_url') || 'http://localhost:9876';
        
        try {
            const headers = {};
            const token = localStorage.getItem('dashboard_token');
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            const response = await fetch(`${baseUrl}/api/bot/channels`, { headers });
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            if (!data.channels || data.channels.length === 0) {
                embedChannelSelect.innerHTML = '<option value="">No channels found</option>';
                return;
            }
            
            embedChannelSelect.innerHTML = data.channels.map(chan => 
                `<option value="${chan.id}">#${chan.name} (${chan.id})</option>`
            ).join('');
            
            embedChannelSelect.disabled = false;
            updateEmbedPreview();
        } catch (err) {
            console.error('Failed to fetch channels:', err);
            embedChannelSelect.innerHTML = `<option value="">⚠️ Connection failed</option>`;
            showToast('Failed to load live channel list', true);
            const details = getDetailedConnectionError(baseUrl, err);
            alert(details);
        }
    }

    if (sendLiveBtn) {
        sendLiveBtn.addEventListener('click', async () => {
            const isLive = localStorage.getItem('enable-live-control') === 'true';
            if (!isLive) return;

            const channelId = embedChannelSelect ? embedChannelSelect.value : '';
            if (!channelId) {
                showToast('Please select a channel from the dropdown list', true);
                return;
            }

            const payload = buildJsonPayload();
            if (Object.keys(payload).length === 0) {
                showToast('Embed payload is empty', true);
                return;
            }

            sendLiveBtn.disabled = true;
            sendLiveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sending...';

            const baseUrl = localStorage.getItem('go_backend_url') || 'http://localhost:9876';

            try {
                const headers = { 'Content-Type': 'application/json' };
                const token = localStorage.getItem('dashboard_token');
                if (token) {
                    headers['Authorization'] = `Bearer ${token}`;
                }
                const response = await fetch(`${baseUrl}/api/bot/embed`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        channel_id: channelId,
                        embed: payload
                    })
                });

                if (!response.ok) {
                    const errData = await response.json().catch(() => ({}));
                    throw new Error(errData.error || `HTTP error ${response.status}`);
                }

                showToast('Embed posted live successfully! 🚀');
            } catch (err) {
                console.error('Failed to post embed live:', err);
                showToast(err.message || 'Failed to post embed live', true);
                const details = getDetailedConnectionError(baseUrl, err);
                alert(details);
            } finally {
                sendLiveBtn.disabled = false;
                sendLiveBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Send Live to Discord';
            }
        });
    }

    // --- Connection Error Diagnostic Helper ---
    function getDetailedConnectionError(url, err) {
        let isHttps = window.location.protocol === 'https:';
        let targetIsHttp = url.startsWith('http://');
        let isLocal = url.includes('localhost') || url.includes('127.0.0.1') || url.includes('::1');
        
        let details = `Error Details: ${err.message || err}\n\n`;
        
        if (isHttps && targetIsHttp && !isLocal) {
            details += `🔒 SECURITY WARNING (Mixed Content Block):\n`;
            details += `You are accessing this dashboard over a secure connection (https://dash.afterworkplay.com), but your Go backend is configured to use unencrypted HTTP (${url}).\n\n`;
            details += `Modern web browsers block HTTPS websites from requesting HTTP endpoints for security reasons.\n\n`;
            details += `HOW TO FIX THIS:\n`;
            details += `1. Access the dashboard over HTTP instead (e.g. http://dash.afterworkplay.com if supported).\n`;
            details += `2. Or, configure SSL for your Go backend using a reverse proxy (like Caddy, Nginx, or a Cloudflare Tunnel) so you can use https:// for the backend URL.`;
        } else {
            details += `🌐 NETWORK / FIREWALL WARNING:\n`;
            details += `The dashboard was unable to contact the backend service at ${url}.\n\n`;
            details += `HOW TO TROUBLESHOOT:\n`;
            details += `1. Verify the service is active on your server: 'sudo systemctl status afterwork'\n`;
            details += `2. Ensure your server's firewall allows port 9876: 'sudo ufw allow 9876'\n`;
            details += `3. Verify that your server IP (${url}) is correct and accessible from your current device (e.g., check if you are on the same local network/VPN).`;
        }
        return details;
    }

    // --- Toast Notification System ---
    let toastTimeout = null;

    function showToast(message, isError = false) {
        toastMessage.textContent = message;
        
        if (isError) {
            toast.style.borderColor = 'var(--accent-red)';
            toast.querySelector('i').className = 'fa-solid fa-circle-xmark';
            toast.querySelector('i').style.color = 'var(--accent-red)';
        } else {
            toast.style.borderColor = 'var(--accent-blue)';
            toast.querySelector('i').className = 'fa-solid fa-circle-check';
            toast.querySelector('i').style.color = 'var(--accent-green)';
        }

        toast.classList.add('show');
        
        if (toastTimeout) clearTimeout(toastTimeout);
        
        toastTimeout = setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    // --- Clipboard Utility ---
    function copyToClipboard(text) {
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard successfully!');
        }).catch(err => {
            console.error('Failed to copy: ', err);
            showToast('Failed to copy text.', true);
        });
    }

    // --- Embed Builder Logic ---

    let embedFieldsList = [];

    // Sync Hex Color inputs
    embedColor.addEventListener('input', (e) => {
        embedColorHex.value = e.target.value;
        updateEmbedPreview();
    });
    
    embedColorHex.addEventListener('input', (e) => {
        let val = e.target.value;
        if (val.startsWith('#') && val.length === 7) {
            embedColor.value = val;
            updateEmbedPreview();
        }
    });

    // Preset color buttons
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const color = btn.getAttribute('data-color');
            embedColor.value = color;
            embedColorHex.value = color;
            updateEmbedPreview();
        });
    });

    // Add Embed Field
    addFieldBtn.addEventListener('click', () => {
        const id = Date.now().toString();
        const fieldData = {
            id: id,
            name: 'Field Title',
            value: 'Field value content...',
            inline: false
        };
        
        embedFieldsList.push(fieldData);
        renderFieldEditorItem(fieldData);
        updateEmbedPreview();
    });

    function renderFieldEditorItem(fieldData) {
        const item = document.createElement('div');
        item.className = 'field-editor-item';
        item.setAttribute('data-id', fieldData.id);
        
        item.innerHTML = `
            <div class="field-inputs">
                <input type="text" class="field-name-input" placeholder="Field Title" value="${fieldData.name}">
                <input type="text" class="field-val-input" placeholder="Field Value" value="${fieldData.value}">
            </div>
            <button type="button" class="btn-delete-field" title="Remove Field">
                <i class="fa-solid fa-trash-can"></i>
            </button>
            <div class="field-options">
                <input type="checkbox" id="inline-${fieldData.id}" class="field-inline-checkbox" ${fieldData.inline ? 'checked' : ''}>
                <label for="inline-${fieldData.id}">Display Inline (side-by-side)</label>
            </div>
        `;
        
        // Add event listeners inside editor item
        item.querySelector('.field-name-input').addEventListener('input', (e) => {
            fieldData.name = e.target.value;
            updateEmbedPreview();
        });
        
        item.querySelector('.field-val-input').addEventListener('input', (e) => {
            fieldData.value = e.target.value;
            updateEmbedPreview();
        });
        
        item.querySelector('.field-inline-checkbox').addEventListener('change', (e) => {
            fieldData.inline = e.target.checked;
            updateEmbedPreview();
        });
        
        item.querySelector('.btn-delete-field').addEventListener('click', () => {
            embedFieldsList = embedFieldsList.filter(f => f.id !== fieldData.id);
            item.remove();
            updateEmbedPreview();
        });
        
        fieldsContainer.appendChild(item);
    }

    // Render Preview
    function updateEmbedPreview() {
        const title = embedTitle.value.trim();
        const desc = embedDescription.value.trim();
        const hexColor = embedColor.value;
        const thumbnail = embedThumbnail.value.trim();
        const image = embedImage.value.trim();
        
        // 1. Set border color
        previewEmbedBorder.style.borderColor = hexColor;
        
        // 2. Set text content
        previewTitle.textContent = title;
        previewTitle.style.display = title ? 'block' : 'none';
        
        previewDescription.textContent = desc;
        previewDescription.style.display = desc ? 'block' : 'none';
        
        // 3. Render thumbnail
        if (thumbnail) {
            previewThumbnail.src = thumbnail;
            previewThumbnailContainer.style.display = 'block';
        } else {
            previewThumbnailContainer.style.display = 'none';
        }
        
        // 4. Render large image
        if (image) {
            previewImage.src = image;
            previewImageContainer.style.display = 'block';
        } else {
            previewImageContainer.style.display = 'none';
        }
        
        // 5. Render fields
        previewFields.innerHTML = '';
        if (embedFieldsList.length > 0) {
            previewFields.style.display = 'grid';
            
            // Determine inline class sizes
            embedFieldsList.forEach(f => {
                const fieldDiv = document.createElement('div');
                fieldDiv.className = 'discord-embed-field';
                if (f.inline) {
                    fieldDiv.classList.add('inline');
                    // Style inline grid logic dynamically
                    fieldDiv.style.gridColumn = 'span 1';
                } else {
                    fieldDiv.style.gridColumn = 'span 2';
                }
                
                fieldDiv.innerHTML = `
                    <div class="field-name">${f.name || 'Field'}</div>
                    <div class="field-value">${f.value || '...'}</div>
                `;
                previewFields.appendChild(fieldDiv);
            });
            
            // Adjust grid template columns based on inline fields presence
            const hasInline = embedFieldsList.some(f => f.inline);
            previewFields.style.gridTemplateColumns = hasInline ? '1fr 1fr' : '1fr';
        } else {
            previewFields.style.display = 'none';
        }

        // 6. Generate paste JSON and final commands
        const payload = buildJsonPayload();
        
        const isLiveMode = localStorage.getItem('enable-live-control') === 'true';
        let channelVal = 'announcements';
        if (isLiveMode) {
            channelVal = (embedChannelSelect && embedChannelSelect.value) || 'announcements';
        } else {
            channelVal = embedChannel.value.trim() || 'announcements';
        }
        
        const formattedCommand = `[p]afterwork embed ${channelVal} ${JSON.stringify(payload)}`;
        
        generatedCommand.textContent = formattedCommand;
    }

    function buildJsonPayload() {
        const title = embedTitle.value.trim();
        const desc = embedDescription.value.trim();
        const hexColor = embedColor.value.replace('#', '0x');
        const thumbnail = embedThumbnail.value.trim();
        const image = embedImage.value.trim();

        const payload = {};
        if (title) payload.title = title;
        if (desc) payload.description = desc;
        if (hexColor) payload.color = hexColor;
        
        if (embedFieldsList.length > 0) {
            payload.fields = embedFieldsList.map(f => ({
                name: f.name || 'Field',
                value: f.value || '...',
                inline: f.inline
            }));
        }
        
        if (thumbnail) payload.thumbnail = thumbnail;
        if (image) payload.image = image;

        return payload;
    }

    // Attach inputs triggers
    [embedChannel, embedTitle, embedDescription, embedThumbnail, embedImage].forEach(input => {
        input.addEventListener('input', updateEmbedPreview);
    });

    // Copy buttons
    copyCmdBtn.addEventListener('click', () => {
        copyToClipboard(generatedCommand.textContent);
    });
    
    copyJsonBtn.addEventListener('click', () => {
        const payload = buildJsonPayload();
        copyToClipboard(JSON.stringify(payload, null, 2));
    });

    // --- RSS Feed Logic ---

    function updateRssCommands() {
        const name = (rssName.value.trim() || 'github-news').toLowerCase().replace(/\s+/g, '-');
        const ch = rssChannel.value.trim() || '#announcements';
        const url = rssUrl.value.trim() || 'https://github.blog/feed/';

        rssAddCmd.textContent = `[p]afterwork rss add "${name}" ${ch} ${url}`;
        rssRemoveCmd.textContent = `[p]afterwork rss remove "${name}"`;
    }

    [rssName, rssChannel, rssUrl].forEach(input => {
        input.addEventListener('input', updateRssCommands);
    });

    copyRssAddBtn.addEventListener('click', () => {
        copyToClipboard(rssAddCmd.textContent);
    });
    
    copyRssRemoveBtn.addEventListener('click', () => {
        copyToClipboard(rssRemoveCmd.textContent);
    });

    // --- Quick Deploy Copier ---
    document.querySelectorAll('.deploy-copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const cmdText = btn.getAttribute('data-copy');
            copyToClipboard(cmdText);
        });
    });

    // --- Initialization ---
    // Render initial sample fields
    const initialFields = [
        { 
            id: '1', 
            name: '🗺️ Server Details', 
            value: 'Name: `AFTERWORK Gaming`\nRegion: `Europe (EU)`', 
            inline: true 
        },
        { 
            id: '2', 
            name: '⚙️ Boosted Settings', 
            value: 'XP: `3X`\nResources: `3X Gathering`', 
            inline: true 
        },
        { 
            id: '3', 
            name: '🚀 How to Join', 
            value: '1. Open the Server Browser.\n2. Switch to the **Experimental** tab.\n3. Search for `AFTERWORK Gaming`.', 
            inline: false 
        }
    ];
    
    initialFields.forEach(f => {
        embedFieldsList.push(f);
        renderFieldEditorItem(f);
    });
    
    // --- Documentation Tab Inner Navigation ---
    const docNavItems = document.querySelectorAll('.doc-nav-item');
    docNavItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = item.getAttribute('data-doc-target');
            const targetEl = document.getElementById(targetId);
            
            if (targetEl) {
                // Highlight active item
                docNavItems.forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                
                // Scroll target element into view
                targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // --- AMP Status Logic ---

    // Load saved API URL from localStorage
    const savedApiUrl = localStorage.getItem('amp_api_url');
    if (savedApiUrl) {
        if (ampApiUrlInput) ampApiUrlInput.value = savedApiUrl;
    }

    if (btnSaveApiUrl) {
        btnSaveApiUrl.addEventListener('click', () => {
            let url = ampApiUrlInput.value.trim();
            if (!url) {
                showToast('Please enter a valid URL', true);
                return;
            }
            if (url.endsWith('/')) {
                url = url.slice(0, -1);
            }
            // Auto-append /api/status if the user only entered the base URL
            if (!url.endsWith('/api/status')) {
                // If it ends with one of the bot paths, replace it
                url = url.replace(/\/api\/bot\/channels\/?$/, '');
                url = url.replace(/\/api\/bot\/embed\/?$/, '');
                url = `${url}/api/status`;
            }
            ampApiUrlInput.value = url;
            localStorage.setItem('amp_api_url', url);
            const token = (ampApiToken && ampApiToken.value.trim()) || '';
            localStorage.setItem('dashboard_token', token);
            if (backendApiToken) {
                backendApiToken.value = token;
            }
            showToast('API Endpoint saved successfully!');
            fetchAmpStatus();
        });
    }

    if (btnRefreshStatus) {
        btnRefreshStatus.addEventListener('click', () => {
            fetchAmpStatus();
        });
    }

    async function fetchAmpStatus() {
        if (!ampApiUrlInput) return;
        const url = ampApiUrlInput.value.trim();
        if (!url) return;

        // Show loader, hide error and grid
        if (ampLoader) ampLoader.style.display = 'flex';
        if (ampError) ampError.style.display = 'none';
        if (serversGrid) serversGrid.innerHTML = '';

        try {
            const controller = new AbortController();
            const id = setTimeout(() => controller.abort(), 8000); // 8 second timeout

            const headers = {};
            const token = localStorage.getItem('dashboard_token');
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const response = await fetch(url, { 
                signal: controller.signal,
                headers: headers
            });
            clearTimeout(id);

            if (!response.ok) {
                throw new Error(`HTTP Error: ${response.status}`);
            }

            const servers = await response.json();
            if (ampLoader) ampLoader.style.display = 'none';

            if (!serversGrid) return;
            if (!Array.isArray(servers) || servers.length === 0) {
                serversGrid.innerHTML = `
                    <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">
                        <i class="fa-solid fa-server" style="font-size: 32px; margin-bottom: 10px; display: block; color: var(--border-color);"></i>
                        <p>No managed servers were found on this AMP instance.</p>
                    </div>
                `;
                return;
            }

            renderServers(servers);
        } catch (err) {
            if (ampLoader) ampLoader.style.display = 'none';
            if (ampError) ampError.style.display = 'flex';
            const details = getDetailedConnectionError(url, err);
            if (ampErrorText) ampErrorText.innerText = details;
            console.error('AMP fetch error:', err);
            alert(details);
        }
    }

    function renderServers(servers) {
        if (!serversGrid) return;
        serversGrid.innerHTML = servers.map(server => {
            const isOnline = server.running;
            const moduleName = server.module || 'Generic';
            
            // Get module icon
            let iconClass = 'fa-solid fa-server';
            const normModule = moduleName.toLowerCase();
            if (normModule.includes('minecraft')) {
                iconClass = 'fa-solid fa-cubes';
            } else if (normModule.includes('rust')) {
                iconClass = 'fa-solid fa-radiation';
            } else if (normModule.includes('ark')) {
                iconClass = 'fa-solid fa-dragon';
            } else if (normModule.includes('valheim') || normModule.includes('enshrouded')) {
                iconClass = 'fa-solid fa-tree';
            } else if (normModule.includes('palworld')) {
                iconClass = 'fa-solid fa-paw';
            } else if (normModule.includes('csgo') || normModule.includes('counterstrike')) {
                iconClass = 'fa-solid fa-crosshairs';
            } else if (normModule.includes('factorio')) {
                iconClass = 'fa-solid fa-industry';
            } else if (normModule.includes('satisfactory')) {
                iconClass = 'fa-solid fa-wrench';
            } else if (normModule.includes('gmod') || normModule.includes('garry')) {
                iconClass = 'fa-solid fa-circle-nodes';
            }

            // Map AMPInstanceState enum values:
            // Stopped = 0, Starting = 1, Running = 2, Stopping = 3, Restarting = 4, Updating = 5, Error = 6, Suspended = 7
            let statusText = 'OFFLINE';
            let statusClass = 'offline';
            let statusIcon = 'fa-circle-xmark';

            const status = server.status;
            if (status === 2) {
                statusText = 'ONLINE';
                statusClass = 'online';
                statusIcon = 'fa-circle-check';
            } else if (status === 1) {
                statusText = 'STARTING';
                statusClass = 'starting';
                statusIcon = 'fa-circle-play';
            } else if (status === 3) {
                statusText = 'STOPPING';
                statusClass = 'stopping';
                statusIcon = 'fa-circle-stop';
            } else if (status === 4) {
                statusText = 'RESTARTING';
                statusClass = 'restarting';
                statusIcon = 'fa-arrows-rotate';
            } else if (status === 5) {
                statusText = 'UPDATING';
                statusClass = 'updating';
                statusIcon = 'fa-cloud-arrow-down';
            } else if (status === 6) {
                statusText = 'ERROR';
                statusClass = 'error';
                statusIcon = 'fa-triangle-exclamation';
            } else if (status === 7) {
                statusText = 'SUSPENDED';
                statusClass = 'suspended';
                statusIcon = 'fa-pause';
            } else {
                if (server.running) {
                    statusText = 'ONLINE';
                    statusClass = 'online';
                    statusIcon = 'fa-circle-check';
                } else {
                    statusText = 'OFFLINE';
                    statusClass = 'offline';
                    statusIcon = 'fa-circle-xmark';
                }
            }

            const playerInfoHtml = (server.max_users > 0)
                ? `<div class="server-card-players" title="Active Players">
                     <i class="fa-solid fa-users"></i>
                     <span>${server.active_users} / ${server.max_users}</span>
                   </div>`
                : '';

            return `
                <div class="server-card">
                    <div class="server-card-header">
                        <div class="server-icon">
                            <i class="${iconClass}"></i>
                        </div>
                        <div class="server-card-header-text">
                            <h4>${server.name}</h4>
                            <span>${moduleName}</span>
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; flex-wrap: wrap; gap: 8px;">
                        <div class="server-card-status ${statusClass}">
                            <i class="fa-solid ${statusIcon}"></i>
                            <span>${statusText}</span>
                        </div>
                        ${playerInfoHtml}
                    </div>
                </div>
            `;
        }).join('');
    }

    updateEmbedPreview();
    updateRssCommands();
});
