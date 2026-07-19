import {createApp} from 'vue';
import {createPinia} from 'pinia';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import 'highlight.js/styles/github.css';
import 'katex/dist/katex.min.css';
import './styles/app.css';
import App from './App.vue';

createApp(App).use(createPinia()).use(ElementPlus).mount('#app');
