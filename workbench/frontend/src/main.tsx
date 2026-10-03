import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './ChatWorkspace.tsx'
import './look-aurora.css'
import './look-console.css'
import { applyTheme, loadTheme } from './theme'

applyTheme(loadTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
