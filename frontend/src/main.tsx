import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import SetupNotice from "./features/auth/SetupNotice";
import { AuthProvider } from "./lib/auth/AuthContext";
import { firebaseConfigured } from "./lib/firebase";
import "./styles/base.css";

/* AuthProvider is mounted only when there is a Firebase project to talk to.
   See lib/firebase.ts: without one, every screen used to vanish behind a blank
   white page, because getAuth() throws during module evaluation rather than
   returning something that fails politely later. */
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {firebaseConfigured ? (
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    ) : (
      <SetupNotice />
    )}
  </StrictMode>,
);
