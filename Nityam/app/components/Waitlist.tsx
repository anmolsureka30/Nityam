"use client";

import { useState, type KeyboardEvent } from "react";
import { APP_LOGIN_URL } from "../lib/config";
import styles from "./styles.module.css";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function Waitlist() {
  const [name, setName] = useState("");
  const [school, setSchool] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const submit = () => {
    const trimmedEmail = email.trim();
    if (!EMAIL_PATTERN.test(trimmedEmail)) {
      setError("Please enter a valid email address.");
      return;
    }
    setError("");
    setSubmitted(true);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") submit();
  };

  return (
    <section id="waitlist" className={styles.waitlistSection}>
      <div className={styles.waitlistInner}>
        <h2 className={styles.waitlistTitle}>Bring Nityam to your school.</h2>
        <p className={styles.waitlistLede}>
          We take on a small number of schools each term and work closely
          with every one of them. Leave your details and we will get in
          touch.
        </p>

        {submitted ? (
          <div className={styles.successCard}>
            <div className={styles.successTitle}>You are on the list.</div>
            <p className={styles.successBody}>
              We will write to you shortly to understand your school and set
              up a walkthrough.
            </p>
          </div>
        ) : (
          <>
            <div className={styles.formRow}>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className={styles.input}
              />
              <input
                type="text"
                value={school}
                onChange={(e) => setSchool(e.target.value)}
                placeholder="School"
                className={styles.input}
              />
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setError("");
                }}
                onKeyDown={handleKeyDown}
                placeholder="Email"
                className={`${styles.input} ${styles.inputEmail}`}
              />
              <button onClick={submit} className={styles.submitBtn}>
                Join the waitlist
              </button>
            </div>
            <div className={styles.formError}>{error}</div>
          </>
        )}

        <p className={styles.waitlistAside}>
          Studying on your own, not through a school?{" "}
          <a href={APP_LOGIN_URL}>Sign in and start now →</a>
        </p>
      </div>
    </section>
  );
}
