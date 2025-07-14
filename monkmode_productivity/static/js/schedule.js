// Schedule-specific functionality
document.addEventListener('DOMContentLoaded', function() {
// Add click handlers for activity completion
    const completeButtons = document.querySelectorAll('.btn-outline-success');
    completeButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();

            if (confirm('Mark this activity as completed?')) {
                this.closest('form').submit();
            }
        });
    });

// Add smooth scrolling to current day
    const today = new Date().toISOString().split('T')[0];
    const todayElement = document.querySelector(`[data-date="${today}"]`);
    if (todayElement) {
        todayElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        todayElement.classList.add('highlight-today');
    }
});
