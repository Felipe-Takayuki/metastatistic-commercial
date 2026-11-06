import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthGate } from "./components/AuthGate";
import "./styles.css";
import { applyThemeMode, loadThemeMode } from "./lib/theme";

applyThemeMode(loadThemeMode()); // antes do 1º render: evita piscar no tema errado
createRoot(document.getElementById("root")!).render(<StrictMode><AuthGate><App /></AuthGate></StrictMode>);
