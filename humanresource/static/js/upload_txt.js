
    document.addEventListener('DOMContentLoaded', function() {
        const toggleButton = document.getElementById('toggle-history-btn');
        const historyContent = document.getElementById('history-content');

        toggleButton.addEventListener('click', function() {
            // Check current visibility state (in a modern browser, display:none is false)
            const isHidden = historyContent.style.display === 'none' || historyContent.style.display === '';
            
            if (isHidden) {
                // Show the content
                historyContent.style.display = 'block';
                toggleButton.innerHTML = '➖ Hide Upload History';
                toggleButton.setAttribute('aria-expanded', 'true');
            } else {
                // Hide the content
                historyContent.style.display = 'none';
                toggleButton.innerHTML = '➕ Show Upload History';
                toggleButton.setAttribute('aria-expanded', 'false');
            }
        });

        // Set the initial state when the page loads (to ensure it's hidden if CSS didn't run)
        historyContent.style.display = 'none';
        
    });
