/* Shown in place of the whole app when frontend/.env has no Firebase config.
 *
 * It replaces a blank white page. Nothing here is styled through the design
 * tokens on purpose: the tokens live in styles/base.css, which this screen can
 * render before, and a setup notice that itself depends on the setup being
 * right is no notice at all. */
export default function SetupNotice() {
  const missing = [
    ["VITE_FIREBASE_API_KEY", import.meta.env.VITE_FIREBASE_API_KEY],
    ["VITE_FIREBASE_AUTH_DOMAIN", import.meta.env.VITE_FIREBASE_AUTH_DOMAIN],
    ["VITE_FIREBASE_PROJECT_ID", import.meta.env.VITE_FIREBASE_PROJECT_ID],
    ["VITE_FIREBASE_STORAGE_BUCKET", import.meta.env.VITE_FIREBASE_STORAGE_BUCKET],
    ["VITE_FIREBASE_MESSAGING_SENDER_ID", import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID],
    ["VITE_FIREBASE_APP_ID", import.meta.env.VITE_FIREBASE_APP_ID],
  ].filter(([, v]) => !v).map(([k]) => k as string);

  return (
    <main style={{
      minHeight: "100vh", display: "grid", placeItems: "center",
      padding: "32px", background: "#12151C", color: "#E8E4DC",
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      fontSize: "14px", lineHeight: 1.65,
    }}>
      <div style={{ maxWidth: "60ch", width: "100%" }}>
        <h1 style={{ fontSize: "18px", margin: "0 0 4px", fontWeight: 600 }}>
          Nityam is not configured yet
        </h1>
        <p style={{ margin: "0 0 22px", color: "#9BA3B0" }}>
          Sign-in needs the Firebase web config, so the app is not starting.
          This is a one-time setup, not an error in the code.
        </p>

        <p style={{ margin: "0 0 6px", color: "#9BA3B0" }}>
          Missing from <code>frontend/.env</code>:
        </p>
        <ul style={{ margin: "0 0 22px", paddingLeft: "18px" }}>
          {missing.map((k) => <li key={k} style={{ color: "#E0A96D" }}>{k}</li>)}
        </ul>

        <p style={{ margin: "0 0 6px", color: "#9BA3B0" }}>Where the values come from:</p>
        <ol style={{ margin: "0 0 22px", paddingLeft: "18px", color: "#C9CFD8" }}>
          <li>Firebase console → your project → Project settings</li>
          <li>Scroll to “Your apps”, pick the web app (or create one)</li>
          <li>Copy the six values out of the <code>firebaseConfig</code> snippet</li>
          <li>
            Paste them into <code>frontend/.env</code> — see{" "}
            <code>frontend/.env.example</code> for the exact names
          </li>
          <li>Restart the dev server; Vite only reads .env at startup</li>
        </ol>

        <p style={{ margin: 0, color: "#6E7684" }}>
          The backend needs its own credentials separately — see{" "}
          <code>backend/.env.example</code>.
        </p>
      </div>
    </main>
  );
}
