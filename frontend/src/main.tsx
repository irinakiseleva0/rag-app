import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AboutPage } from './components/AboutPage'

// /about is a hidden page: no link to it anywhere in the app.
const isAbout = window.location.pathname.replace(/\/+$/, '') === '/about'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isAbout ? <AboutPage /> : <App />}
  </StrictMode>,
)
