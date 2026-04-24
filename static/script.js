document.getElementById('generateForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const rawThought = document.getElementById('rawThought').value.trim();
    if (!rawThought) return;

    const btn = document.getElementById('submitBtn');
    const spinner = document.querySelector('.spinner');
    const btnText = document.querySelector('.btn-text');
    const statusSection = document.getElementById('statusSection');
    const statusText = document.getElementById('statusText');
    const resultSection = document.getElementById('resultSection');
    const errorSection = document.getElementById('errorSection');
    const progressFill = document.getElementById('progressFill');

    // Reset UI
    btn.disabled = true;
    spinner.style.display = 'block';
    btnText.textContent = 'Processing...';
    statusSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    progressFill.style.width = '10%';
    
    // Polling function to get updates
    let pollInterval = setInterval(async () => {
        try {
            const res = await fetch('/status');
            const data = await res.json();
            if(data.status) {
                statusText.textContent = data.status;
                if(data.progress) {
                    progressFill.style.width = `${data.progress}%`;
                }
            }
        } catch(err) {
            console.error('Status fetch failed', err);
        }
    }, 1500);

    try {
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ raw_thought: rawThought })
        });

        const data = await response.json();
        
        clearInterval(pollInterval);
        progressFill.style.width = '100%';

        if (data.success) {
            statusSection.style.display = 'none';
            resultSection.style.display = 'block';
            document.getElementById('resultCaption').textContent = data.caption;
            
            const videoElement = document.getElementById('resultVideo');
            const sourceElement = document.getElementById('videoSource');
            
            // Add a cache buster so browser reloads it if it's new
            sourceElement.src = data.video_url + '?t=' + new Date().getTime();
            videoElement.load();
        } else {
            statusSection.style.display = 'none';
            errorSection.style.display = 'block';
            document.getElementById('errorText').textContent = data.error || 'Failed to generate video.';
        }
    } catch (err) {
        clearInterval(pollInterval);
        statusSection.style.display = 'none';
        errorSection.style.display = 'block';
        document.getElementById('errorText').textContent = 'A network error occurred: ' + err.message;
    } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
        btnText.textContent = 'Generate Short Video';
    }
});
