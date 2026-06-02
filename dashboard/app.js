// Afterwork Dashboard Controller Logic

document.addEventListener('DOMContentLoaded', () => {
    // --- Navigation System ---
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const tabTitle = document.getElementById('tab-title');
    const tabSubtitle = document.getElementById('tab-subtitle');

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
        });
    });

    // --- Toast Notification System ---
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');
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
    const embedChannel = document.getElementById('embed-channel');
    const embedTitle = document.getElementById('embed-title');
    const embedDescription = document.getElementById('embed-description');
    const embedColor = document.getElementById('embed-color');
    const embedColorHex = document.getElementById('embed-color-hex');
    const embedThumbnail = document.getElementById('embed-thumbnail');
    const embedImage = document.getElementById('embed-image');
    
    const addFieldBtn = document.getElementById('add-field-btn');
    const fieldsContainer = document.getElementById('fields-container');
    
    // Preview fields
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
        const channelVal = embedChannel.value.trim() || 'announcements';
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
    const rssName = document.getElementById('rss-name');
    const rssChannel = document.getElementById('rss-channel');
    const rssUrl = document.getElementById('rss-url');
    
    const rssAddCmd = document.getElementById('rss-add-cmd');
    const rssRemoveCmd = document.getElementById('rss-remove-cmd');
    
    const copyRssAddBtn = document.getElementById('copy-rss-add-btn');
    const copyRssRemoveBtn = document.getElementById('copy-rss-remove-btn');

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
        { id: '1', name: 'Server Details', value: 'IP: `play.afterworkplay.com`\nRegion: `US-East`', inline: true },
        { id: '2', name: 'Modpack Version', value: 'Version: `v2.4.1` (Latest)', inline: true }
    ];
    
    initialFields.forEach(f => {
        embedFieldsList.push(f);
        renderFieldEditorItem(f);
    });

    updateEmbedPreview();
    updateRssCommands();
});
