document.addEventListener('alpine:init', () => {
    Alpine.data('bookProbe', () => ({
        count: 0,
        loading: false,
        requests: 0,

        async probe() {
            this.loading = true;

            const response = await fetch('/api/books/', {headers: {'X-Requested-With': 'XMLHttpRequest'}});
            const payload = await response.json();

            this.count = payload.count;
            this.loading = false;
            this.requests += 1;
        }
    }));
});
