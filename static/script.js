document.getElementById('generateForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const rawThought = document.getElementById('rawThought').value.trim();
    if (!rawThought) return;

    const btn           = document.getElementById('submitBtn');
    const spinner       = document.querySelector('.spinner');
    const btnText       = document.querySelector('.btn-text');
    const statusSection = document.getElementById('statusSection');
    const statusText    = document.getElementById('statusText');
    const resultSection = document.getElementById('resultSection');
    const errorSection  = document.getElementById('errorSection');
    const progressFill  = document.getElementById('progressFill');

    // ── Reset UI ──────────────────────────────────────────────────────────────
    btn.disabled = true;
    spinner.style.display   = 'block';
    btnText.textContent     = 'Processing...';
    statusSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display  = 'none';
    progressFill.style.width    = '5%';

    function showError(msg) {
        statusSection.style.display = 'none';
        errorSection.style.display  = 'block';
        document.getElementById('errorText').textContent = msg;
    }

    function resetBtn() {
        btn.disabled            = false;
        spinner.style.display   = 'none';
        btnText.textContent     = 'Generate Short Video';
    }

    // ── Step 1: kick off the job (returns immediately) ────────────────────────
    let startRes, startData;
    try {
        startRes  = await fetch('/generate', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ raw_thought: rawThought }),
        });
        startData = await startRes.json();
    } catch (err) {
        showError('Network error starting job: ' + err.message);
        resetBtn();
        return;
    }

    if (!startData.success) {
        showError(startData.error || 'Failed to start generation.');
        resetBtn();
        return;
    }

    // ── Step 2: poll /status until progress hits 100 ──────────────────────────
    await new Promise((resolve, reject) => {
        const poll = setInterval(async () => {
            try {
                const res  = await fetch('/status');
                const data = await res.json();

                if (data.status) statusText.textContent = data.status;
                if (data.progress != null) progressFill.style.width = `${data.progress}%`;

                // Surface backend errors mid-job
                if (data.error) {
                    clearInterval(poll);
                    reject(new Error(data.error));
                    return;
                }

                if (data.progress >= 100) {
                    clearInterval(poll);
                    resolve();
                }
            } catch (err) {
                // Don't stop polling on a single failed status fetch
                console.warn('Status poll failed (will retry):', err.message);
            }
        }, 1000);
    }).catch(err => {
        showError(err.message || 'Something went wrong during generation.');
        resetBtn();
        return Promise.reject(err); // stop execution below
    });

    // ── Step 3: fetch the finished result ─────────────────────────────────────
    let result;
    try {
        const res = await fetch('/result');
        result    = await res.json();
    } catch (err) {
        showError('Could not fetch the finished video: ' + err.message);
        resetBtn();
        return;
    }

    if (!result.ready) {
        showError(result.error || 'Video not ready — try refreshing.');
        resetBtn();
        return;
    }

    // ── Step 4: show the video ────────────────────────────────────────────────
    progressFill.style.width    = '100%';
    statusSection.style.display = 'none';
    resultSection.style.display = 'block';

    document.getElementById('resultCaption').textContent = result.caption;

    const videoEl  = document.getElementById('resultVideo');
    const sourceEl = document.getElementById('videoSource');

    // Cache-bust so the browser doesn't serve a stale file if the URL is reused
    sourceEl.src = result.video_url + '?t=' + Date.now();
    videoEl.load();

    resetBtn();
});