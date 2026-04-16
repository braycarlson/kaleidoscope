import { createApp } from 'vue';
import App from './App.vue';
import './main.css';

const host = document.getElementById('ks-app');

if (!host) {
    throw new Error('Kaleidoscope mount point #ks-app not found');
}

const shadow = host.attachShadow({ mode: 'open' });

const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = '/__kaleidoscope__/static/kaleidoscope.css';

const root = document.createElement('div');

link.addEventListener('load', function() {
    shadow.appendChild(root);
    createApp(App).mount(root);
});

shadow.appendChild(link);
