import { createApp } from 'vue';
import App from './App.vue';
import './main.css';

const host = document.getElementById('ks-app');

if (!host) {
    throw new Error('Kaleidoscope mount point #ks-app not found');
}

const launch = host.dataset['launch'] ?? '';
const shadow = host.attachShadow({ mode: 'open' });
const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = '/__kaleidoscope__/static/kaleidoscope.css';

const root = document.createElement('div');

function app_mount() {
    if (root.parentNode !== null) return;

    shadow.appendChild(root);
    createApp(App, { launch: launch }).mount(root);
}

link.addEventListener('load', app_mount);
link.addEventListener('error', app_mount);

shadow.appendChild(link);
