import { createRoot } from "react-dom/client";
import App from "./App.jsx";

// Deliberately not wrapped in StrictMode: it double-invokes effects in dev,
// which would open two WebSockets and two AudioContexts and make the mic
// behave strangely for no useful reason in a media app.
createRoot(document.getElementById("root")).render(<App />);
