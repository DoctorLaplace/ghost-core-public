require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const { app, BrowserWindow, globalShortcut } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let win;
let pythonProcess;

function createWindow() {
    const isOverlay = (process.env.OVERLAY_MODE || 'False').toLowerCase() === 'true';

    win = new BrowserWindow({
        width: 1200,
        height: 800,
        transparent: isOverlay,
        frame: !isOverlay,
        fullscreen: isOverlay,
        alwaysOnTop: isOverlay,
        skipTaskbar: isOverlay,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    if (isOverlay) {
        // Enforce maximum z-index priority on Windows so it stays above other applications
        win.setAlwaysOnTop(true, 'screen-saver');
    }

    const indexPath = path.join(__dirname, 'src', 'index.html');

    if (isOverlay) {
        win.loadFile(indexPath, { query: { "overlay": "true" } });
    } else {
        win.loadFile(indexPath);
    }

    // Developer Tooling Override
    // win.webContents.openDevTools({ mode: 'detach' });
}

function startPythonBackend() {
    const backendPath = path.join(__dirname, '..', 'main.py');
    pythonProcess = spawn('python', [backendPath], {
        cwd: path.join(__dirname, '..')
    });

    let isOverlayVisible = true;

    pythonProcess.stdout.on('data', (data) => {
        const output = data.toString();
        // Check for hardware manipulation commands gracefully injected into standard output
        if (output.includes("[ELECTRON] HIDE")) {
            if (win) {
                win.setIgnoreMouseEvents(true, { forward: true });
                win.setAlwaysOnTop(false);
            }
        } else if (output.includes("[ELECTRON] SHOW")) {
            if (win) {
                const isOverlay = (process.env.OVERLAY_MODE || 'False').toLowerCase() === 'true';
                win.setIgnoreMouseEvents(false);
                if (isOverlay) {
                    win.setAlwaysOnTop(true, 'screen-saver');
                }
                win.show();
                win.focus();
            }
        }
        console.log(`[Python]: ${output}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        const output = data.toString();
        // Python logging often writes to stderr even for INFO level messages.
        if (output.includes("ERROR") || output.includes("CRITICAL") || output.includes("Exception:") || output.includes("Traceback")) {
            console.error(`[Python ERROR]: ${output}`);
        } else {
            console.log(`[Python INFO]: ${output.trim()}`);
        }
    });

    pythonProcess.on('close', (code) => {
        console.log(`Python process exited with code ${code}`);
        if (code === 42) {
            console.log("Rebooting Python backend...");
            startPythonBackend();
        } else if (code === 99) {
            console.log("Shutdown signal received. Quitting Electron app...");
            app.quit();
        }
    });
}

app.whenReady().then(() => {
    startPythonBackend();

    // Give Python server a moment to start before loading UI
    setTimeout(() => {
        createWindow();
    }, 4000);

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });

    // --- Hard Quit Fail-Safe ---
    globalShortcut.register('CommandOrControl+Shift+Q', () => {
        console.log("HARD QUIT hotkey pressed. Force closing the application.");
        if (pythonProcess) {
            try {
                process.kill(pythonProcess.pid, 'SIGINT'); // Try graceful kill first
                pythonProcess.kill('SIGKILL'); // Hard kill fallback
            } catch (e) { }
        }
        app.quit();
    });
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    if (pythonProcess) {
        pythonProcess.kill();
    }
});
