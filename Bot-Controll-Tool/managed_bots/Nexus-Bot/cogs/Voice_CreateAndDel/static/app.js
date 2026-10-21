// cogs/VoiceCreator/static/app.js
// Main JavaScript file for Voice Creator Panel

// Main initialization function
function initializeApp() {
    // ==== TAB FUNCTIONALITY ====
    window.openTab = function(evt, tabName) {
        var tabcontents = document.getElementsByClassName("tabcontent");
        for (var i = 0; i < tabcontents.length; i++) {
            tabcontents[i].classList.remove("visible");
        }
        
        var tablinks = document.getElementsByClassName("tablinks");
        for (var i = 0; i < tablinks.length; i++) {
            tablinks[i].classList.remove("active");
        }
        
        document.getElementById(tabName).classList.add("visible");
        evt.currentTarget.classList.add("active");
    };

    // ==== MODAL FUNCTIONS ====
    window.openModal = function(modalId) {
        document.getElementById(modalId).classList.add('show');
    };

    window.closeModal = function(modalId) {
        document.getElementById(modalId).classList.remove('show');
    };

    // ==== CHANNEL TEMPLATES ====
    let channelTemplates = [];

    function loadChannelTemplates() {
        fetch('/api/channel-templates')
            .then(response => response.json())
            .then(data => {
                channelTemplates = data;
                renderChannelTemplates();
            })
            .catch(error => console.error('Error loading channel templates:', error));
    }

    function renderChannelTemplates() {
        const container = document.getElementById('channelTemplatesContainer');
        if (!container) return;
        
        container.innerHTML = '';
        
        if (channelTemplates.length === 0) {
            container.innerHTML = '<p>No custom templates defined yet. Click "Add New Template" to create one.</p>';
            return;
        }
        
        for (let i = 0; i < channelTemplates.length; i++) {
            const template = channelTemplates[i];
            const card = document.createElement('div');
            card.className = 'channel-card';
            
            card.innerHTML = `
                <div class="channel-card-header">
                    <h3>${template.name || 'Unnamed Template'}</h3>
                    <div class="actions">
                        <button class="btn-small" onclick="editTemplate(${template.id})">Edit</button>
                        <button class="btn-small btn-danger" onclick="deleteTemplate(${template.id})">Delete</button>
                    </div>
                </div>
                <div class="form-group">
                    <label>Format:</label>
                    <p>${template.format || 'Default format'}</p>
                </div>
            `;
            
            container.appendChild(card);
        }
    }

    window.editTemplate = function(templateId) {
        const template = channelTemplates.find(t => t.id === templateId);
        if(!template) return;
        
        document.getElementById('templateId').value = template.id;
        document.getElementById('templateName').value = template.name || '';
        document.getElementById('modalChannelFormat').value = template.format || '';
        
        openModal('editChannelModal');
    };

    window.deleteTemplate = function(templateId) {
        if (confirm('Are you sure you want to delete this template?')) {
            fetch(`/api/channel-templates/${templateId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadChannelTemplates();
                } else {
                    alert('Error deleting template: ' + data.error);
                }
            })
            .catch(error => console.error('Error deleting template:', error));
        }
    };

    // ==== LOAD JOIN CHANNELS DATA ====
    function loadJoinChannels() {
        fetch('/api/join-channels')
            .then(response => response.json())
            .then(data => {
                const tbody = document.getElementById('joinChannelsBody');
                if (!tbody) return;
                tbody.innerHTML = '';

                if (data.length === 0) {
                    return;
                }
                
                const channelIds = data.map(ch => ch.id);
                const categoryIds = data.map(ch => ch.categoryId);
                
                Promise.all([
                    fetch('/api/channel-names?ids=' + channelIds.join(',')).then(r => r.json()),
                    fetch('/api/channel-names?ids=' + categoryIds.join(',')).then(r => r.json())
                ])
                .then(([channelNames, categoryNames]) => {
                    tbody.innerHTML = '';
                    data.forEach(channel => {
                        const row = document.createElement('tr');
                        const formatType = channel.useSequential ? 'Sequential' : 'Username-based';
                        row.innerHTML = `
                            <td>${channel.id}</td>
                            <td>${channelNames[channel.id] || 'Unknown'}</td>
                            <td>${channel.categoryId}</td>
                            <td>${categoryNames[channel.categoryId] || 'Unknown'}</td>
                            <td>${channel.channelFormat || 'Default'}</td>
                            <td>${formatType}</td>
                            <td class="actions">
                                <button class="btn-small btn-danger" onclick="removeJoinChannel('${channel.id}')">Remove</button>
                            </td>`;
                        tbody.appendChild(row);
                    });
                });
            })
            .catch(error => console.error('Error loading join channels:', error));
    }

    window.removeJoinChannel = function(channelId) {
        if (confirm('Are you sure you want to remove this join channel?')) {
            fetch(`/api/join-channels/${channelId}`, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                if (data.success) loadJoinChannels();
                else alert('Error: ' + data.error);
            });
        }
    };

    function loadMessageDeleteSettings() {
        fetch('/api/message-delete-settings')
            .then(response => response.json())
            .then(data => {
                document.getElementById('deleteChannelId1').value = data.channel1?.id || '';
                document.getElementById('deleteChannelId2').value = data.channel2?.id || '';
                document.getElementById('deleteChannelId3').value = data.channel3?.id || '';
                
                document.getElementById('time1').value = data.channel1?.minutes || 10;
                document.getElementById('time2').value = data.channel2?.minutes || 1440;
                document.getElementById('time3').value = data.channel3?.minutes || 10080;
                
                document.getElementById('deleteEmptyChannels').checked = data.deleteEmptyChannels === 'true';
                document.getElementById('showDeleteWarning').checked = data.showDeleteWarning === 'true';
                
                if (data.useSequentialNames === 'true') {
                    document.getElementById('sequentialMode').checked = true;
                    document.getElementById('sequentialSettings').style.display = 'block';
                } else {
                    document.getElementById('userNameMode').checked = true;
                    document.getElementById('sequentialSettings').style.display = 'none';
                }
                
                document.getElementById('userChannelFormat').value = data.userChannelFormat || "{username}'s Channel";
                document.getElementById('sequentialChannelFormat').value = data.sequentialChannelFormat || "-Room{number}-";
            })
            .catch(error => console.error('Error loading settings:', error));
    }
    
    function setupSequentialModeToggle() {
        document.querySelectorAll('input[name="namingMode"]').forEach(radio => {
            radio.addEventListener('change', function() {
                document.getElementById('sequentialSettings').style.display = 
                    document.getElementById('sequentialMode').checked ? 'block' : 'none';
            });
        });
    }

    function setupAddVoiceChannelForm() {
        document.getElementById('addVoiceChannelForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const payload = {
                joinChannelId: document.getElementById('joinChannelId').value,
                categoryId: document.getElementById('categoryId').value,
                channelFormat: document.getElementById('channelFormat').value,
                useSequential: document.getElementById('useSequential').checked
            };
            fetch('/api/join-channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    this.reset();
                    loadJoinChannels();
                } else alert('Error: ' + data.error);
            });
        });
    }

    function setupSaveSettingsButton() {
        document.getElementById('saveSettings').addEventListener('click', function() {
            const payload = {
                deleteEmptyChannels: document.getElementById('deleteEmptyChannels').checked,
                showDeleteWarning: document.getElementById('showDeleteWarning').checked,
                useSequentialNames: document.getElementById('sequentialMode').checked,
                userChannelFormat: document.getElementById('userChannelFormat').value,
                sequentialChannelFormat: document.getElementById('sequentialChannelFormat').value
            };
            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) alert('Settings saved!');
                else alert('Error: ' + data.error);
            });
        });
    }

    function setupResetCounterButton() {
        document.getElementById('resetCounter').addEventListener('click', function() {
            if (confirm('Are you sure you want to reset the room counter to 0?')) {
                fetch('/api/reset-counter', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) alert('Counter reset!');
                    else alert('Error: ' + data.error);
                });
            }
        });
    }

    function setupAddTemplateButton() {
        document.getElementById('addNewTemplate').addEventListener('click', function() {
            document.getElementById('templateId').value = '';
            document.getElementById('channelDesignForm').reset();
            openModal('editChannelModal');
        });
    }

    function setupChannelDesignForm() {
        document.getElementById('channelDesignForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const id = document.getElementById('templateId').value;
            const payload = {
                name: document.getElementById('templateName').value,
                format: document.getElementById('modalChannelFormat').value
            };
            const url = id ? `/api/channel-templates/${id}` : '/api/channel-templates';
            const method = id ? 'PUT' : 'POST';
            
            fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    closeModal('editChannelModal');
                    loadChannelTemplates();
                } else alert('Error: ' + data.error);
            });
        });
    }

    function setupAutoDeleteForms() {
        for (let i = 1; i <= 3; i++) {
            document.getElementById(`autoDeleteForm${i}`).addEventListener('submit', function(e) {
                e.preventDefault();
                saveDeleteChannel(i, document.getElementById(`deleteChannelId${i}`).value, document.getElementById(`time${i}`).value);
            });
        }
    }

    function saveDeleteChannel(slot, channelId, minutes) {
        fetch('/api/message-delete-channel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slot, channelId, minutes })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) alert(`Channel ${slot} settings saved!`);
            else alert('Error: ' + data.error);
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        initializeApp();
    });

    // Load initial data and set up handlers
    loadJoinChannels();
    loadMessageDeleteSettings();
    loadChannelTemplates();
    setupSequentialModeToggle();
    setupAddVoiceChannelForm();
    setupSaveSettingsButton();
    setupResetCounterButton();
    setupAddTemplateButton();
    setupChannelDesignForm();
    setupAutoDeleteForms();
}

// Check if running in browser before executing
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    initializeApp();
}