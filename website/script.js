// Wait for DOM to load
document.addEventListener('DOMContentLoaded', () => {
    
    // Intersection Observer for scroll animations
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                // Optional: stop observing once it has faded in
                // observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Select all elements with the fade-in class
    const fadeElements = document.querySelectorAll('.fade-in');
    fadeElements.forEach(el => observer.observe(el));

    // Dynamic Mockup Progress Bar Animation
    const progressBar = document.querySelector('.tc-progress-fill');
    if (progressBar) {
        let progress = 45;
        setInterval(() => {
            progress += Math.random() * 2;
            if (progress > 100) progress = 0;
            progressBar.style.width = `${progress}%`;
        }, 1500);
    }
});
