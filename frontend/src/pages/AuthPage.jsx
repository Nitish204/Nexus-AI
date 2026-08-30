import { useEffect, useRef, useState, useCallback } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sparkles, Environment } from "@react-three/drei";
import { API_BASE } from "../utils/api";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID;

const SECURITY_QUESTIONS = [
  "What city were you born in?",
  "What was the name of your first pet?",
  "What is your mother's maiden name?",
  "What was the model of your first car?",
  "What elementary school did you attend?",
];

function friendlyError(err) {
  const msg = err?.message || "";
  if (msg === "Failed to fetch" || msg === "Load failed" || msg === "NetworkError when attempting to fetch resource.") {
    return "Couldn't reach the server. It may be offline or still deploying — please try again in a moment.";
  }
  return msg || "Something went wrong.";
}

function CenterGem({ pointer }) {
  const meshRef = useRef();
  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (meshRef.current) {
      meshRef.current.rotation.y = t * 0.25 + pointer.current.x * 0.7;
      meshRef.current.rotation.x = Math.sin(t * 0.3) * 0.2 + pointer.current.y * 0.5;
      const s = 1 + Math.sin(t * 1.1) * 0.06;
      meshRef.current.scale.set(s, s, s);
    }
  });
  return (
    <Float speed={2.2} rotationIntensity={0.6} floatIntensity={1.4}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1.5, 8]} />
        <MeshDistortMaterial
          color="#ff5fa2"
          emissive="#ff2d92"
          emissiveIntensity={0.35}
          roughness={0.15}
          metalness={0.6}
          distort={0.45}
          speed={2.2}
        />
      </mesh>
    </Float>
  );
}

function OrbitGem({ radius, offset, scale, color, speed }) {
  const groupRef = useRef();
  const meshRef = useRef();
  useFrame((state) => {
    const t = state.clock.getElapsedTime() * speed + offset;
    if (groupRef.current) {
      groupRef.current.position.x = Math.cos(t) * radius;
      groupRef.current.position.z = Math.sin(t) * radius;
      groupRef.current.position.y = Math.sin(t * 1.4) * 0.6;
    }
    if (meshRef.current) {
      meshRef.current.rotation.x += 0.01;
      meshRef.current.rotation.y += 0.014;
    }
  });
  return (
    <group ref={groupRef}>
      <Float speed={3} rotationIntensity={1} floatIntensity={1.6}>
        <mesh ref={meshRef} scale={scale}>
          <octahedronGeometry args={[1, 0]} />
          <MeshDistortMaterial color={color} emissive={color} emissiveIntensity={0.4} distort={0.3} speed={3} roughness={0.2} metalness={0.4} />
        </mesh>
      </Float>
    </group>
  );
}

function Scene() {
  const pointer = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const handleMove = (e) => {
      pointer.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", handleMove);
    return () => window.removeEventListener("pointermove", handleMove);
  }, []);

  return (
    <Canvas camera={{ position: [0, 0, 6], fov: 50 }}>
      <ambientLight intensity={0.9} />
      <pointLight position={[4, 4, 4]} intensity={2} color="#ffd166" />
      <pointLight position={[-4, -2, 3]} intensity={1.6} color="#ff5fa2" />
      <pointLight position={[0, -3, -3]} intensity={1} color="#8b5cf6" />
      <CenterGem pointer={pointer} />
      <OrbitGem radius={3.4} offset={0} scale={0.35} color="#ffd166" speed={0.6} />
      <OrbitGem radius={2.8} offset={2.1} scale={0.25} color="#8b5cf6" speed={0.8} />
      <OrbitGem radius={3.9} offset={4.2} scale={0.3} color="#4dd8ff" speed={0.5} />
      <Sparkles count={80} scale={9} size={3} speed={0.5} color="#ffffff" opacity={0.6} />
      <Environment preset="sunset" />
    </Canvas>
  );
}

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [mounted, setMounted] = useState(false);
  const googleButtonRef = useRef(null);

  const [forgotStep, setForgotStep] = useState("email");
  const [forgotEmail, setForgotEmail] = useState("");
  const [securityQuestion, setSecurityQuestion] = useState("");
  const [securityAnswer, setSecurityAnswer] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [resetDone, setResetDone] = useState(false);

  const [securityQuestionChoice, setSecurityQuestionChoice] = useState(SECURITY_QUESTIONS[0]);
  const [securityAnswerSignup, setSecurityAnswerSignup] = useState("");

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const saveSession = (data) => {
    localStorage.setItem("nexus_user", JSON.stringify(data.user));
    onAuthenticated(data);
  };

  const handleEmailSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!email.trim() || !password) {
      setError("Please fill in both email and password.");
      return;
    }
    if (mode === "signup" && !securityAnswerSignup.trim()) {
      setError("Please answer the security question.");
      return;
    }

    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/signup";
      const body =
        mode === "login"
          ? { email, password }
          : {
              email,
              password,
              name,
              security_question: securityQuestionChoice,
              security_answer: securityAnswerSignup,
            };
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      saveSession(data);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleFetchQuestion = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/security-question?email=${encodeURIComponent(forgotEmail)}`, {
        credentials: "include",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      setSecurityQuestion(data.security_question);
      setForgotStep("answer");
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleResetSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (newPassword !== newPasswordConfirm) {
      setError("Passwords don't match.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/reset-password-direct`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: forgotEmail,
          security_answer: securityAnswer,
          new_password: newPassword,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      setResetDone(true);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  const backToLogin = () => {
    setForgotStep("email");
    setForgotEmail("");
    setSecurityQuestion("");
    setSecurityAnswer("");
    setNewPassword("");
    setNewPasswordConfirm("");
    setResetDone(false);
    setError("");
    setMode("login");
  };

  const handleGoogleCredential = useCallback(async (response) => {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ id_token: response.credential }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Google sign-in failed.");
      saveSession(data);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      /* global google */
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleGoogleCredential,
      });

      let attempts = 0;
      const tryRender = () => {
        attempts += 1;
        if (googleButtonRef.current) {
          window.google.accounts.id.renderButton(googleButtonRef.current, {
            theme: "filled_blue",
            size: "large",
            shape: "pill",
            width: 320,
          });
        } else if (attempts < 10) {
          setTimeout(tryRender, 150);
        }
      };
      tryRender();
    };
    document.body.appendChild(script);
    return () => document.body.removeChild(script);
  }, [handleGoogleCredential]);

  const handleGitHubLogin = () => {
    const state = crypto.randomUUID();
    sessionStorage.setItem("nexus_github_oauth_state", state);
    const redirectUri = window.location.origin;
    const url = `https://github.com/login/oauth/authorize?client_id=${GITHUB_CLIENT_ID}&redirect_uri=${encodeURIComponent(
      redirectUri
    )}&scope=read:user user:email&state=${encodeURIComponent(state)}`;
    window.location.href = url;
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const returnedState = params.get("state");
    if (!code) return;

    const expectedState = sessionStorage.getItem("nexus_github_oauth_state");
    sessionStorage.removeItem("nexus_github_oauth_state");
    if (!expectedState || returnedState !== expectedState) {
      setError("GitHub sign-in couldn't be verified (state mismatch) — please try again.");
      const url = new URL(window.location.href);
      url.searchParams.delete("code");
      url.searchParams.delete("state");
      window.history.replaceState({}, "", url);
      return;
    }

    (async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/auth/github`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ code }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "GitHub sign-in failed.");
        const url = new URL(window.location.href);
        url.searchParams.delete("code");
        url.searchParams.delete("state");
        window.history.replaceState({}, "", url);
        saveSession(data);
      } catch (err) {
        setError(friendlyError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const switchMode = () => {
    setSwitching(true);
    setError("");
    setTimeout(() => {
      setMode((m) => (m === "login" ? "signup" : "login"));
      setSwitching(false);
    }, 220);
  };

  return (
    <div
      style={{
        width: "100vw",
        height: "100dvh",
        position: "relative",
        overflow: "hidden",
        fontFamily: "'Space Grotesk', 'Segoe UI', sans-serif",
        background: "linear-gradient(120deg, #ff5fa2 0%, #ff8a5c 28%, #ffd166 55%, #8b5cf6 82%, #4dd8ff 100%)",
        backgroundSize: "300% 300%",
        animation: "nexusGradient 16s ease infinite",
      }}
    >
      <style>{`
        @keyframes nexusGradient {
          0% { background-position: 0% 40%; }
          50% { background-position: 100% 60%; }
          100% { background-position: 0% 40%; }
        }
        @keyframes cardIn {
          0% { opacity: 0; transform: translateY(40px) scale(0.92) rotateX(8deg); }
          100% { opacity: 1; transform: translateY(0) scale(1) rotateX(0deg); }
        }
        @keyframes brandFloat {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-6px); }
        }
        @keyframes fadeSlide {
          0% { opacity: 0; transform: translateX(10px); }
          100% { opacity: 1; transform: translateX(0); }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes pulseGlow {
          0%, 100% { box-shadow: 0 0 22px #ff5fa266, 0 12px 40px #00000033; }
          50% { box-shadow: 0 0 38px #ffd16688, 0 12px 40px #00000033; }
        }
        .nexus-card { perspective: 1200px; }
        .nexus-primary-btn:hover { transform: translateY(-2px) scale(1.015); box-shadow: 0 10px 30px #ff5fa266; }
        .nexus-primary-btn:active { transform: translateY(0) scale(0.98); }
        .nexus-secondary-btn:hover { transform: translateY(-1px); border-color: #ffffff88; background: #ffffff14; }
        .nexus-social-btn { transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease; }
        @media (prefers-reduced-motion: reduce) {
          * { animation: none !important; transition: none !important; }
        }
      `}</style>

      <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>
        <Scene />
      </div>

      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 1,
          background:
            "radial-gradient(circle at 30% 30%, #ffffff22 0%, transparent 55%)",
          pointerEvents: "none",
        }}
      />

      <div
        style={{
          position: "absolute",
          top: 24,
          left: 24,
          zIndex: 2,
          color: "#fff",
          animation: "brandFloat 4s ease-in-out infinite",
        }}
      >
        <div
          style={{
            fontSize: "clamp(20px, 4vw, 28px)",
            fontWeight: 800,
            letterSpacing: 1,
            textShadow: "0 2px 20px #ff5fa288, 0 0 2px #fff",
          }}
        >
          NEXUS
        </div>
        <div style={{ fontSize: 12, color: "#ffffffcc", marginTop: 4, fontWeight: 500 }}>
          Autonomous AI developer workspace
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 2,
          display: "flex",
          alignItems: "center",
          justifyContent: window.innerWidth < 768 ? "center" : "flex-end",
          padding: "16px",
        }}
      >
        <div
          className="nexus-card"
          style={{
            width: "100%",
            maxWidth: 380,
            marginRight: window.innerWidth < 768 ? 0 : "6vw",
          }}
        >
          <div
            style={{
              padding: "clamp(22px, 5vw, 34px)",
              borderRadius: 24,
              background: "rgba(255, 255, 255, 0.85)",
              backdropFilter: "blur(20px)",
              WebkitBackdropFilter: "blur(20px)",
              border: "1px solid #ffffffaa",
              color: "#241533",
              maxHeight: "92dvh",
              overflowY: "auto",
              opacity: mounted ? (switching ? 0.4 : 1) : 0,
              animation: mounted ? "cardIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both, pulseGlow 5s ease-in-out infinite" : "none",
              transform: switching ? "scale(0.97)" : "scale(1)",
              transition: "transform 0.22s ease, opacity 0.22s ease",
            }}
          >
            {mode === "forgot" ? (
              resetDone ? (
                <>
                  <h2 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#241533" }}>Password updated</h2>
                  <p style={{ fontSize: 13, color: "#5c4a70", marginTop: 6, marginBottom: 22 }}>
                    You can now sign in with your new password.
                  </p>
                  <button
                    onClick={backToLogin}
                    className="nexus-primary-btn"
                    style={{
                      width: "100%",
                      padding: "13px 16px",
                      borderRadius: 12,
                      border: "none",
                      background: "linear-gradient(135deg, #ff5fa2, #ffd166)",
                      color: "#241533",
                      fontWeight: 800,
                      fontSize: 15,
                      cursor: "pointer",
                    }}
                  >
                    Back to sign in
                  </button>
                </>
              ) : forgotStep === "email" ? (
                <>
                  <h2 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#241533" }}>Reset your password</h2>
                  <p style={{ fontSize: 13, color: "#5c4a70", marginTop: 6, marginBottom: 22 }}>
                    Enter your account email to continue. No email will be sent — you'll verify with your
                    security question instead.
                  </p>
                  <form onSubmit={handleFetchQuestion}>
                    <FloatingInput label="Email" value={forgotEmail} onChange={setForgotEmail} type="email" />
                    {error && <div style={{ color: "#e0245e", fontSize: 12, marginBottom: 12, fontWeight: 600 }}>{error}</div>}
                    <button
                      type="submit"
                      disabled={loading}
                      className="nexus-primary-btn"
                      style={{
                        width: "100%",
                        padding: "13px 16px",
                        borderRadius: 12,
                        border: "none",
                        background: "linear-gradient(135deg, #ff5fa2, #ffd166)",
                        color: "#241533",
                        fontWeight: 800,
                        fontSize: 15,
                        cursor: loading ? "default" : "pointer",
                      }}
                    >
                      {loading ? "Checking..." : "Continue"}
                    </button>
                    <div style={{ textAlign: "center", marginTop: 16, fontSize: 13, color: "#5c4a70" }}>
                      <span onClick={backToLogin} style={{ color: "#e0246e", cursor: "pointer", fontWeight: 800 }}>
                        ← Back to sign in
                      </span>
                    </div>
                  </form>
                </>
              ) : (
                <>
                  <h2 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#241533" }}>Verify & set a new password</h2>
                  <p style={{ fontSize: 13, color: "#5c4a70", marginTop: 6, marginBottom: 18 }}>
                    Answer your security question, then choose a new password.
                  </p>
                  <form onSubmit={handleResetSubmit}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "#241533",
                        background: "#24153310",
                        padding: "10px 14px",
                        borderRadius: 10,
                        marginBottom: 14,
                      }}
                    >
                      {securityQuestion}
                    </div>
                    <FloatingInput label="Your answer" value={securityAnswer} onChange={setSecurityAnswer} type="text" />
                    <FloatingInput label="New password" value={newPassword} onChange={setNewPassword} type="password" />
                    <FloatingInput label="Confirm new password" value={newPasswordConfirm} onChange={setNewPasswordConfirm} type="password" />
                    {error && <div style={{ color: "#e0245e", fontSize: 12, marginBottom: 12, fontWeight: 600 }}>{error}</div>}
                    <button
                      type="submit"
                      disabled={loading}
                      className="nexus-primary-btn"
                      style={{
                        width: "100%",
                        padding: "13px 16px",
                        borderRadius: 12,
                        border: "none",
                        background: "linear-gradient(135deg, #ff5fa2, #ffd166)",
                        color: "#241533",
                        fontWeight: 800,
                        fontSize: 15,
                        cursor: loading ? "default" : "pointer",
                      }}
                    >
                      {loading ? "Updating..." : "Update password"}
                    </button>
                    <div style={{ textAlign: "center", marginTop: 16, fontSize: 13, color: "#5c4a70" }}>
                      <span onClick={backToLogin} style={{ color: "#e0246e", cursor: "pointer", fontWeight: 800 }}>
                        ← Back to sign in
                      </span>
                    </div>
                  </form>
                </>
              )
            ) : (
              <>
                <h2
                  style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#241533", animation: "fadeSlide 0.35s ease" }}
                  key={mode + "-title"}
                >
                  {mode === "login" ? "Welcome back" : "Create your account"}
                </h2>
                <p style={{ fontSize: 13, color: "#5c4a70", marginTop: 6, marginBottom: 22 }}>
                  {mode === "login" ? "Sign in to continue building." : "Join NEXUS and start building."}
                </p>

                <div ref={googleButtonRef} style={{ marginBottom: 12, display: "flex", justifyContent: "center" }} />

                <button
                  onClick={handleGitHubLogin}
                  type="button"
                  className="nexus-social-btn"
                  style={{
                    width: "100%",
                    padding: "11px 16px",
                    borderRadius: 999,
                    border: "1px solid #24153322",
                    background: "#241533",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 8,
                    marginBottom: 20,
                  }}
                >
                  <svg width="18" height="18" viewBox="0 0 16 16" fill="#fff">
                    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
                  </svg>
                  Continue with GitHub
                </button>

                <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "16px 0" }}>
                  <div style={{ flex: 1, height: 1, background: "#24153322" }} />
                  <span style={{ fontSize: 11, color: "#5c4a7099", fontWeight: 600 }}>or</span>
                  <div style={{ flex: 1, height: 1, background: "#24153322" }} />
                </div>

                <form onSubmit={handleEmailSubmit} key={mode + "-form"} style={{ animation: "fadeSlide 0.4s ease" }}>
                  {mode === "signup" && (
                    <FloatingInput label="Name" value={name} onChange={setName} type="text" />
                  )}
                  <FloatingInput label="Email" value={email} onChange={setEmail} type="email" />
                  <FloatingInput label="Password" value={password} onChange={setPassword} type="password" />

                  {mode === "signup" && (
                    <>
                      <div style={{ marginBottom: 10 }}>
                        <label style={{ fontSize: 11.5, fontWeight: 700, color: "#5c4a70", display: "block", marginBottom: 6 }}>
                          Security question (used to reset your password later — no email required)
                        </label>
                        <select
                          value={securityQuestionChoice}
                          onChange={(e) => setSecurityQuestionChoice(e.target.value)}
                          style={{
                            width: "100%",
                            padding: "11px 12px",
                            borderRadius: 10,
                            border: "1px solid #24153322",
                            background: "#ffffffcc",
                            color: "#241533",
                            fontFamily: "inherit",
                            fontSize: 13.5,
                            outline: "none",
                          }}
                        >
                          {SECURITY_QUESTIONS.map((q) => (
                            <option key={q} value={q}>
                              {q}
                            </option>
                          ))}
                        </select>
                      </div>
                      <FloatingInput label="Your answer" value={securityAnswerSignup} onChange={setSecurityAnswerSignup} type="text" />
                    </>
                  )}

                  {mode === "login" && (
                    <div style={{ textAlign: "right", marginTop: -10, marginBottom: 16 }}>
                      <span
                        onClick={() => {
                          setError("");
                          setMode("forgot");
                        }}
                        style={{ color: "#5c4a70", cursor: "pointer", fontWeight: 600, fontSize: 12 }}
                      >
                        Forgot password?
                      </span>
                    </div>
                  )}

                  {error && (
                    <div style={{ color: "#e0245e", fontSize: 12, marginBottom: 12, fontWeight: 600 }}>{error}</div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="nexus-primary-btn"
                    style={{
                      width: "100%",
                      padding: "13px 16px",
                      borderRadius: 12,
                      border: "none",
                      background: "linear-gradient(135deg, #ff5fa2, #ffd166)",
                      color: "#241533",
                      fontWeight: 800,
                      fontSize: 15,
                      cursor: loading ? "default" : "pointer",
                      marginTop: 4,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 8,
                      transition: "transform 0.2s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.2s ease",
                    }}
                  >
                    {loading && (
                      <span
                        style={{
                          width: 14,
                          height: 14,
                          borderRadius: "50%",
                          border: "2px solid #24153355",
                          borderTopColor: "#241533",
                          display: "inline-block",
                          animation: "spin 0.7s linear infinite",
                        }}
                      />
                    )}
                    {loading ? "Please wait..." : mode === "login" ? "Sign In" : "Create Account"}
                  </button>
                </form>

                <div style={{ textAlign: "center", marginTop: 20, fontSize: 13, color: "#5c4a70" }}>
                  {mode === "login" ? "Don't have an account? " : "Already have an account? "}
                  <span onClick={switchMode} style={{ color: "#e0246e", cursor: "pointer", fontWeight: 800 }}>
                    {mode === "login" ? "Sign up" : "Sign in"}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FloatingInput({ label, value, onChange, type }) {
  const [focused, setFocused] = useState(false);
  const active = focused || value.length > 0;
  return (
    <div style={{ position: "relative", marginBottom: 18 }}>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={{
          width: "100%",
          padding: "14px 12px 8px 12px",
          borderRadius: 10,
          border: `1.5px solid ${focused ? "#ff5fa2" : "#24153322"}`,
          background: "#ffffffb0",
          color: "#241533",
          fontFamily: "inherit",
          fontSize: 14,
          outline: "none",
          boxShadow: focused ? "0 0 0 4px #ff5fa222" : "none",
          transition: "all 0.25s ease",
        }}
      />
      <label
        style={{
          position: "absolute",
          left: 12,
          top: active ? 2 : "50%",
          transform: active ? "translateY(0) scale(0.72)" : "translateY(-50%) scale(1)",
          transformOrigin: "left top",
          color: active ? "#e0246e" : "#5c4a7099",
          fontSize: 12,
          fontWeight: 600,
          pointerEvents: "none",
          transition: "all 0.2s ease",
        }}
      >
        {label}
      </label>
    </div>
  );
}
