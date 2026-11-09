import React from "react";
import { createRoot } from "react-dom/client";
import { ModuleRegistry, AllCommunityModule } from "ag-grid-community";
import App from "./App.jsx";
import "./styles.css";
ModuleRegistry.registerModules([AllCommunityModule]);
createRoot(document.getElementById("root")).render(<App />);
