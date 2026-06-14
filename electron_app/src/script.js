document.addEventListener("DOMContentLoaded", () => {
    const logContainer = document.getElementById("log-container");
    const commandForm = document.getElementById("command-form");
    const commandInput = document.getElementById("command-input");
    const statusIndicator = document.getElementById("status-indicator");
    const statusText = document.getElementById("status-text");

    const leftPanel = document.getElementById("left-panel");
    const rightPanel = document.getElementById("right-panel");
    const toggleLeftBtn = document.getElementById("toggle-left-btn");
    const toggleRightBtn = document.getElementById("toggle-right-btn");
    const closeLeftBtn = document.getElementById("close-left-btn");
    const closeRightBtn = document.getElementById("close-right-btn");

    const leftDragHandle = document.getElementById("left-drag-handle");
    const rightDragHandle = document.getElementById("right-drag-handle");

    const thoughtStream = document.getElementById("thought-stream");
    const workspaceView = document.getElementById("workspace-view");
    const goalTree = document.getElementById("goal-tree");
    const memoryViewer = document.getElementById("memory-viewer");
    const ltmViewer = document.getElementById("ltm-viewer");
    const loadedToolsCount = document.getElementById("loaded-tools-count");
    const toolsList = document.getElementById("loaded-tools-list");
    const statusTooltip = document.getElementById("status-tooltip");

    const btnWipe = document.getElementById("btn-wipe");
    const btnHalt = document.getElementById("btn-halt");
    const btnShutdown = document.getElementById("btn-shutdown");

    const toggleSettingsBtn = document.getElementById("toggle-settings-btn");
    const closeSettingsBtn = document.getElementById("close-settings-btn");
    const saveSettingsBtn = document.getElementById("save-settings-btn");
    const settingsModal = document.getElementById("settings-modal");
    const modelSelect = document.getElementById("model-select");
    const personaSelect = document.getElementById("persona-select");

    let ws;
    let hasConnectedOnce = false;

    // --- Panel Toggles ---
    toggleLeftBtn.addEventListener("click", () => leftPanel.classList.toggle("open"));
    closeLeftBtn.addEventListener("click", () => leftPanel.classList.remove("open"));
    toggleRightBtn.addEventListener("click", () => rightPanel.classList.toggle("open"));
    closeRightBtn.addEventListener("click", () => rightPanel.classList.remove("open"));

    // --- Settings Modal Toggles ---
    if (toggleSettingsBtn) {
        toggleSettingsBtn.addEventListener("click", () => settingsModal.classList.add("active"));
    }
    if (closeSettingsBtn) {
        closeSettingsBtn.addEventListener("click", () => settingsModal.classList.remove("active"));
    }
    if (settingsModal) {
        settingsModal.addEventListener("click", (e) => {
            if (e.target === settingsModal) {
                settingsModal.classList.remove("active");
            }
        });
    }
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener("click", () => {
            const newModel = modelSelect.value;
            const newPersona = personaSelect ? personaSelect.value : null;
            const routingToggle = document.getElementById("routing-toggle");
            const routingEnabled = routingToggle ? routingToggle.checked : true;
            if (ws && ws.readyState === WebSocket.OPEN) {
                const payload = JSON.stringify({
                    type: "change_model",
                    model: newModel,
                    persona: newPersona,
                    routing_enabled: routingEnabled
                });
                ws.send(payload);
                addLogEntry(`Applying system settings: Model -> ${newModel}, Persona -> ${newPersona}, Routing -> ${routingEnabled}`, "system");
                settingsModal.classList.remove("active");
            }
        });
    }

    // --- Panel Resizing Logic ---
    function setupResizer(panel, handle, isLeft) {
        if (!handle) return;

        let isDragging = false;
        let startX, startWidth;

        handle.addEventListener('mousedown', (e) => {
            if (!panel.classList.contains("open")) return;
            isDragging = true;
            startX = e.clientX;

            // Get current width
            startWidth = parseInt(window.getComputedStyle(panel).width, 10);

            panel.classList.add('dragging');
            document.body.style.cursor = 'ew-resize';
            document.body.style.userSelect = 'none'; // Prevent text selection
        });

        window.addEventListener('mousemove', (e) => {
            if (!isDragging) return;

            let newWidth;
            if (isLeft) {
                newWidth = startWidth + (e.clientX - startX);
            } else {
                newWidth = startWidth - (e.clientX - startX);
            }

            // Enforce hard constraint matching original CSS
            if (newWidth < 450) newWidth = 450;
            // Prevent pushing the center feed completely off-screen
            if (newWidth > window.innerWidth * 0.7) newWidth = window.innerWidth * 0.7;

            if (isLeft) {
                document.documentElement.style.setProperty('--left-panel-width', `${newWidth}px`);
            } else {
                document.documentElement.style.setProperty('--right-panel-width', `${newWidth}px`);
            }
        });

        window.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            panel.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        });
    }

    setupResizer(leftPanel, leftDragHandle, true);
    setupResizer(rightPanel, rightDragHandle, false);

    function connectWebSocket() {
        if (!hasConnectedOnce) {
            statusText.textContent = "INITIALIZING";
            statusIndicator.className = "status-disconnected";
            statusIndicator.style.animation = "pulse 1.5s infinite";
        } else {
            statusText.textContent = "RETRYING CONNECTION";
            statusIndicator.className = "status-disconnected";
            statusIndicator.style.animation = "pulse 1.5s infinite";
        }

        // In Electron, file:// protocol has no host. Fallback to the Python Uvicorn port.
        const host = window.location.host || "127.0.0.1:8000";
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${wsProtocol}//${host}/ws`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            hasConnectedOnce = true;
            updateStatus(true);
            statusIndicator.style.animation = "none";
            addLogEntry("Connection to Ghost Core established.", "system");
            ws.send("_ui_sync"); // Request current state to populate panels

            // Send active state synchronization message to tell backend the overlay's current visibility
            const isOverlayHidden = document.body.classList.contains('fade-out');
            ws.send(JSON.stringify({
                type: "ui_state",
                is_hidden: isOverlayHidden
            }));
        };

        ws.onmessage = (event) => {
            handleIncomingMessage(event.data);
        };

        ws.onclose = () => {
            if (!hasConnectedOnce) {
                statusText.textContent = "INITIALIZING";
                statusIndicator.className = "status-disconnected";
                statusIndicator.style.animation = "pulse 1.5s infinite";
            } else {
                updateStatus(false);
            }
            addLogEntry("Connection lost. Retrying in 3s...", "system");
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (error) => {
            // Suppress the explicit error log as the browser natively logs connection failures.
            ws.close();
        };
    }

    function updateStatus(isConnected) {
        if (isConnected) {
            statusIndicator.className = "status-connected";
            statusText.textContent = "ONLINE";
            const onlineTheme = (window.FLUID_CONFIG && window.FLUID_CONFIG.THEME) || 'default';
            if (window.fluid && window.fluid.setTheme) {
                window.fluid.setTheme(onlineTheme);
            }
        } else {
            statusIndicator.className = "status-disconnected";
            statusText.textContent = "OFFLINE";
            if (window.fluid && window.fluid.setTheme) {
                window.fluid.setTheme('offline');
            }
        }
    }

    function addLogEntry(message, type = "action") {
        const logEntry = document.createElement("div");

        logEntry.classList.add("log-entry");
        if (type) {
            const classes = type.split(" ");
            classes.forEach(cls => logEntry.classList.add(cls));
        }

        const content = document.createElement("div");
        content.classList.add("message-content");
        content.textContent = message;

        logEntry.appendChild(content);
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function appendToTerminalFeed(message, type) {
        const entry = document.createElement("div");
        entry.className = `log-entry ${type}`;

        const content = document.createElement("div");
        content.classList.add("message-content");
        content.textContent = `[${type.toUpperCase()}] ${message}`;

        entry.appendChild(content);
        thoughtStream.appendChild(entry);
        thoughtStream.scrollTop = thoughtStream.scrollHeight;
    }

    function renderGoalTree(goalsDict) {
        goalTree.innerHTML = "";
        if (Object.keys(goalsDict).length === 0) {
            goalTree.innerHTML = "<div style='color: var(--text-muted)'>No active goals.</div>";
            return;
        }

        for (const goalId in goalsDict) {
            const goal = goalsDict[goalId];
            if (goal.status === "completed") continue;

            const goalDiv = document.createElement("div");
            const displayTitle = goal.title || goal.description;
            goalDiv.innerHTML = `<strong>Goal:</strong> ${displayTitle} [${goal.status.toUpperCase()}]`;
            goalTree.appendChild(goalDiv);

            goal.root_tasks.forEach(task => renderTaskNode(task, goalTree, 1));
        }
    }

    function renderTaskNode(task, parentElement, indentLevel) {
        const indentSpan = "&nbsp;&nbsp;".repeat(indentLevel);
        const taskDiv = document.createElement("div");
        const statusColor = task.status === "in_progress" ? "var(--accent-cyan)" :
            task.status === "failed" ? "var(--accent-red)" :
                task.status === "completed" ? "var(--accent-green)" : "var(--text-muted)";

        taskDiv.innerHTML = `${indentSpan} ↳ <span style="color:${statusColor}; font-weight: bold;">[${task.status.toUpperCase()}]</span> ${task.description}`;
        parentElement.appendChild(taskDiv);

        task.subtasks.forEach(subtask => renderTaskNode(subtask, parentElement, indentLevel + 1));
    }

    function renderMemory(memoryList) {
        memoryViewer.innerHTML = "";
        if (memoryList.length === 0) {
            memoryViewer.innerHTML = "<div style='color: var(--text-muted)'>STM is empty.</div>";
            return;
        }
        memoryList.forEach(mem => {
            const memDiv = document.createElement("div");
            memDiv.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
            memDiv.style.padding = "4px 0";

            const sourceSpan = document.createElement("span");
            sourceSpan.style.color = "var(--accent-cyan)";
            sourceSpan.textContent = `[${mem.source}] `;

            const textSpan = document.createElement("span");
            textSpan.textContent = mem.text;

            memDiv.appendChild(sourceSpan);
            memDiv.appendChild(textSpan);
            memoryViewer.appendChild(memDiv);
        });
        memoryViewer.scrollTop = memoryViewer.scrollHeight;
    }

    function renderLTM(memoryList) {
        ltmViewer.innerHTML = "";
        if (memoryList.length === 0) {
            ltmViewer.innerHTML = "<div style='color: var(--text-muted)'>LTM is empty.</div>";
            return;
        }
        memoryList.forEach(mem => {
            const memDiv = document.createElement("div");
            memDiv.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
            memDiv.style.padding = "6px 0";
            memDiv.style.cursor = "pointer";

            const headerDiv = document.createElement("div");
            headerDiv.style.display = "flex";
            headerDiv.style.alignItems = "baseline";

            const scoreSpan = document.createElement("span");
            scoreSpan.style.color = "var(--accent-purple)";
            scoreSpan.textContent = `[LTM::${mem.relevance_score || '?'}] `;
            scoreSpan.style.marginRight = "6px";

            const titleSpan = document.createElement("span");
            titleSpan.style.fontWeight = "bold";
            titleSpan.style.color = "var(--text-main)";
            titleSpan.textContent = mem.title || "Untitled Memory Node";
            titleSpan.style.flex = "1";

            headerDiv.appendChild(scoreSpan);
            headerDiv.appendChild(titleSpan);

            const contentDiv = document.createElement("div");
            contentDiv.style.display = "none";
            contentDiv.style.marginTop = "6px";
            contentDiv.style.paddingLeft = "10px";
            contentDiv.style.borderLeft = "2px solid rgba(255,255,255,0.1)";

            const sourceSpan = document.createElement("div");
            sourceSpan.style.color = "rgba(255,255,255,0.4)";
            sourceSpan.style.fontSize = "0.85em";
            sourceSpan.textContent = `Source: [${mem.source || 'unknown'}] `;
            sourceSpan.style.marginBottom = "4px";

            const textSpan = document.createElement("div");
            textSpan.textContent = mem.text || "Empty memory node";
            textSpan.style.color = "var(--text-muted)";
            textSpan.style.fontSize = "0.9em";
            textSpan.style.whiteSpace = "pre-wrap";

            contentDiv.appendChild(sourceSpan);
            contentDiv.appendChild(textSpan);

            memDiv.appendChild(headerDiv);
            memDiv.appendChild(contentDiv);

            // Toggle Logic
            memDiv.addEventListener('click', () => {
                if (contentDiv.style.display === "none") {
                    contentDiv.style.display = "block";
                    titleSpan.style.color = "var(--accent-cyan)";
                } else {
                    contentDiv.style.display = "none";
                    titleSpan.style.color = "var(--text-main)";
                }
            });

            ltmViewer.appendChild(memDiv);
        });
        ltmViewer.scrollTop = ltmViewer.scrollHeight;
    }

    function renderTools(toolList) {
        toolsList.innerHTML = "";
        loadedToolsCount.textContent = toolList.length;
        toolList.forEach(tool => {
            const div = document.createElement("div");
            div.className = "tool-item";
            div.textContent = tool;
            toolsList.appendChild(div);
        });
    }

    function updatePulseIndicator(state) {
        statusTooltip.textContent = `Agent is: ${state.toUpperCase()}`;
        if (state === "thinking") {
            statusIndicator.className = "status-connected";
            statusIndicator.style.animation = "pulse 1s infinite";
            statusText.textContent = "THINKING";
        } else if (state === "error") {
            statusIndicator.className = "status-disconnected";
            statusIndicator.style.animation = "none";
            statusText.textContent = "ERROR";
        } else {
            statusIndicator.className = "status-connected";
            statusIndicator.style.animation = "none";
            statusText.textContent = "ONLINE";
        }
    }

    function handleIncomingMessage(rawMessage) {
        let payload;
        try {
            payload = JSON.parse(rawMessage);
        } catch (e) {
            // Fallback for non-JSON strings just in case
            if (rawMessage.startsWith("Director command received:")) return;
            addLogEntry(rawMessage, "system");
            return;
        }

        const type = payload.type;
        const data = payload.data;

        switch (type) {
            case "system":
            case "error":
                addLogEntry(data, type);
                // Highlight final response specifically if present
                if (typeof data === 'string' && data.toLowerCase().includes("task complete. final response:")) {
                    const latestEntry = logContainer.lastElementChild;
                    if (latestEntry) {
                        latestEntry.className = "log-entry agent";
                    }
                }
                break;
            case "thought":
            case "action":
                appendToTerminalFeed(data, type);
                break;
            case "metacognition":
                addLogEntry(data, type);
                break;
            case "goal_update":
                renderGoalTree(data);
                break;
            case "workspace_update":
                workspaceView.textContent = data || "Workspace empty.";
                break;
            case "memory_update":
                renderMemory(data);
                break;
            case "ltm_update":
                renderLTM(data);
                break;
            case "tool_update":
                renderTools(data);
                break;
            case "status_ping":
                updatePulseIndicator(data);
                break;
            case "hotkey":
                if (data === "toggle_overlay") {
                    const willHide = !document.body.classList.contains('fade-out');
                    if (willHide) {
                        document.body.classList.add('fade-out');
                        // Suspend focus mode if active
                        if (document.body.classList.contains('focus-mode')) {
                            document.body.dataset.restoreFocus = "true";
                            document.body.classList.remove('focus-mode');
                        }
                    } else {
                        document.body.classList.remove('fade-out');
                        // Restore focus mode if suspended
                        if (document.body.dataset.restoreFocus === "true") {
                            document.body.classList.add('focus-mode');
                            document.body.dataset.restoreFocus = "false";
                        }
                        // Focus the input when showing the overlay
                        setTimeout(() => commandInput.focus(), 100);
                    }
                } else if (data === "toggle_focus") {
                    if (document.body.classList.contains('fade-out')) {
                        // Ignore focus mode toggles while the UI is hidden
                        return;
                    }
                    document.body.classList.toggle('focus-mode');
                }
                break;
            case "config_update":
                if (data && data.model_name) {
                    const select = document.getElementById("model-select");
                    if (select) {
                        select.value = data.model_name;
                    }
                }
                if (data && data.router_enabled !== undefined) {
                    const toggle = document.getElementById("routing-toggle");
                    if (toggle) {
                        toggle.checked = data.router_enabled;
                    }
                }
                break;
            default:
                console.warn("Unknown event type:", type);
        }
    }

    commandForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const command = commandInput.value.trim();
        if (command && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(command);
            addLogEntry(command, "director");

            // Gold Bloom Effect
            if (window.fluid && window.fluid.triggerComplexSplat) {
                // Gold Palette (Dark, Mid, Light, Highlight, Red Accent)
                const goldPalette = [
                    { r: 0.57, g: 0.42, b: 0.08 }, // #926C15 Dark
                    { r: 0.83, g: 0.68, b: 0.21 }, // #D4AF37 Mid
                    { r: 1.0, g: 0.84, b: 0.0 },   // #FFD700 Light
                    { r: 1.0, g: 0.76, b: 0.0 },   // #FFC300 Highlight
                    { r: 0.44, g: 0.18, b: 0.21 }  // #722F37 Red Accent
                ];

                const splatConfig = {
                    startX: 0.95,
                    startY: 0.5,
                    dirX: -1.0,
                    dirY: 0.0,
                    forceScale: window.FLUID_CONFIG.DIRECTOR_PLUME_FORCE_SCALE || 0.4,
                    bloomScale: window.FLUID_CONFIG.DIRECTOR_PLUME_BLOOM_SCALE || 1.0
                };
                window.fluid.triggerComplexSplat(goldPalette, splatConfig);
            }

            commandInput.value = "";
            commandInput.style.height = "auto";
        } else if (command) {
            addLogEntry("Cannot transmit. No active connection.", "error");
        }
    });

    // Keyboard shortcuts: Ctrl+Enter to submit, Shift+Enter for new line
    commandInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            if (e.ctrlKey) {
                // Ctrl+Enter: Submit the form
                e.preventDefault();
                commandForm.dispatchEvent(new Event("submit"));
            } else if (!e.shiftKey) {
                // Plain Enter without Shift: Also submit
                e.preventDefault();
                commandForm.dispatchEvent(new Event("submit"));
            }
            // Shift+Enter: Allow default behavior (new line)
        }
    });

    // Auto-resize textarea as content grows
    commandInput.addEventListener("input", () => {
        commandInput.style.height = "auto";
        commandInput.style.height = Math.min(commandInput.scrollHeight, 120) + "px";
    });

    // --- Power Controls ---
    btnWipe?.addEventListener("click", () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send("_wipe_and_restart");
        }
    });

    btnHalt?.addEventListener("click", () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send("_halt");
        }
    });

    btnShutdown?.addEventListener("click", () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send("_shutdown");
        }
    });

    connectWebSocket();
});