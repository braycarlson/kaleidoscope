import { createApp } from 'vue';
import App from './App.vue';
import './main.css';

const host = document.getElementById('ks-app')!;
const shadow = host.attachShadow({ mode: 'open' });

const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = '/__kaleidoscope__/static/kaleidoscope.css';
shadow.appendChild(link);

const root = document.createElement('div');
shadow.appendChild(root);

createApp(App).mount(root);
