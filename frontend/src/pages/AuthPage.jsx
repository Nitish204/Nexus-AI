import { useEffect, useRef, useState, useCallback } from "react";
import { Canvas, useFrame } from "@react-three/fiber";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID;

// ---------- 3D Orb ----------
function Orb({ pointer }) {
  const meshRef = useRef();
  const particlesRef = useRef();

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (meshRef.current) {
      meshRef.current.rotation.y = t * 0.15 + pointer.current.x * 0.6;
      meshRef.current.rotation.x = pointer.current.y * 0.4;
      const scale = 1 + Math.sin(t * 0.8) * 0.03;
      meshRef.current.scale.set(scale, scale, scale);
    }
    if (particlesRef.current) {
      particlesRef.current.rotation.y = -t * 0.08;
    }
  });

  return (
    <group>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1.6, 2]} />
        <meshStandardMaterial
          color="#00d9ff"
          emissive="#0099cc"
          emissiveIntensity={0.6}
          wireframe
          transparent
          opacity={0.8}
        />
      </mesh>
      <points ref={particlesRef}>
        <sphereGeometry args={[2.4, 48, 48]} />
        <pointsMaterial size={0.02} color="#39ffe0" transparent opacity={0.5} sizeAttenuation />
      </points>
    </group>
  );
}

function OrbScene() {
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
    <Canvas camera={{ position: [0, 0, 5], fov: 50 }}>
      <ambientLight intensity={0.5} />
      <pointLight position={[3, 3, 3]} intensity={1.4} color="#00d9ff" />
      <pointLight position={[-3, -2, 2]} intensity={0.8} color="#39ffe0" />
      <Orb pointer={pointer} />
    </Canvas>
  );
}

// ---------- Auth Card ----------
export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const googleButtonRef = useRef(null);

  const saveSession = (data) => {
    localStorage.setItem("nexus_token", data.access_token);
    localStorage.setItem("nexus_user", JSON.stringify(data.user));
    onAuthenticated(data);
  };

  const handleEmailSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/signup";
      const body = mode === "login" ? { email, password } : { email, password, name };
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      saveSession(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleCredential = useCallback(async (response) => {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: response.credential }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Google sign-in failed.");
      saveSession(data);
    } catch (err) {
      setError(err.message);
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
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        theme: "filled_black",
        size: "large",
        shape: "pill",
        width: 320,
      });
    };
    document.body.appendChild(script);
    return () => document.body.removeChild(script);
  }, [handleGoogleCredential]);

  const handleGitHubLogin = () => {
    const redirectUri = window.location.origin;
    const url = `https://github.com/login/oauth/authorize?client_id=${GITHUB_CLIENT_ID}&redirect_uri=${encodeURIComponent(
      redirectUri
    )}&scope=read:user user:email`;
    window.location.href = url;
  };

  // Handle GitHub redirect back with ?code=...
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (!code) return;
    (async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/auth/github`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "GitHub sign-in failed.");
        const url = new URL(window.location.href);
        url.searchParams.delete("code");
        window.history.replaceState({}, "", url);
        saveSession(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div
      style={{
        width: "100vw",
        height: "100dvh",
        display: "flex",
        background: "#05060a",
        overflow: "hidden",
        fontFamily: "monospace",
      }}
    >
      {/* Left: 3D orb */}
      <div style={{ flex: 1, position: "relative", display: window.innerWidth < 768 ? "none" : "block" }}>
        <OrbScene />
        <div
          style={{
            position: "absolute",
            bottom: 40,
            left: 40,
            color: "#e6faff",
            maxWidth: 320,
          }}
        >
          <div style={{ fontSize: 28, fontWeight: 700, color: "#00d9ff", letterSpacing: 1 }}>NEXUS</div>
          <div style={{ fontSize: 13, color: "#8fd9ec99", marginTop: 6 }}>
            Autonomous AI developer workspace
          </div>
        </div>
      </div>

      {/* Right: auth card */}
      <div
        style={{
          flex: "0 0 min(480px, 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 380,
            padding: 32,
            borderRadius: 20,
            background: "rgba(10, 13, 20, 0.55)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            border: "1px solid transparent",
            backgroundImage:
              "linear-gradient(rgba(10,13,20,0.55), rgba(10,13,20,0.55)), linear-gradient(135deg, #00d9ff55, #39ffe022, #ff6b3533)",
            backgroundOrigin: "border-box",
            backgroundClip: "padding-box, border-box",
            boxShadow: "0 0 60px #00d9ff11, 0 20px 60px #00000066",
            transition: "all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
            color: "#e6faff",
          }}
        >
          <h2 style={{ margin: 0, fontSize: 22, color: "#00d9ff" }}>
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h2>
          <p style={{ fontSize: 12, color: "#8fd9ec99", marginTop: 6, marginBottom: 24 }}>
            {mode === "login" ? "Sign in to continue building." : "Join NEXUS and start building."}
          </p>

          <div ref={googleButtonRef} style={{ marginBottom: 12, display: "flex", justifyContent: "center" }} />

          <button
            onClick={handleGitHubLogin}
            type="button"
            style={{
              width: "100%",
              padding: "10px 16px",
              borderRadius: 999,
              border: "1px solid #ffffff33",
              background: "#161b22",
              color: "#e6faff",
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
            <div style={{ flex: 1, height: 1, background: "#ffffff22" }} />
            <span style={{ fontSize: 11, color: "#8fd9ec66" }}>or</span>
            <div style={{ flex: 1, height: 1, background: "#ffffff22" }} />
          </div>

          <form onSubmit={handleEmailSubmit}>
            {mode === "signup" && (
              <FloatingInput label="Name" value={name} onChange={setName} type="text" />
            )}
            <FloatingInput label="Email" value={email} onChange={setEmail} type="email" />
            <FloatingInput label="Password" value={password} onChange={setPassword} type="password" />

            {error && (
              <div style={{ color: "#ff6b35", fontSize: 12, marginBottom: 12 }}>{error}</div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                padding: "12px 16px",
                borderRadius: 10,
                border: "none",
                background: "linear-gradient(135deg, #00d9ff, #39ffe0)",
                color: "#05060a",
                fontWeight: 700,
                cursor: "pointer",
                marginTop: 4,
              }}
            >
              {loading ? "Please wait..." : mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>

          <div style={{ textAlign: "center", marginTop: 20, fontSize: 12, color: "#8fd9ec99" }}>
            {mode === "login" ? "Don't have an account? " : "Already have an account? "}
            <span
              onClick={() => {
                setMode(mode === "login" ? "signup" : "login");
                setError("");
              }}
              style={{ color: "#00d9ff", cursor: "pointer", fontWeight: 700 }}
            >
              {mode === "login" ? "Sign up" : "Sign in"}
            </span>
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
        required
        style={{
          width: "100%",
          padding: "14px 12px 8px 12px",
          borderRadius: 8,
          border: `1px solid ${focused ? "#00d9ff" : "#ffffff33"}`,
          background: "#0a0d14aa",
          color: "#e6faff",
          fontFamily: "monospace",
          fontSize: 14,
          outline: "none",
          boxShadow: focused ? "0 0 12px #00d9ff44" : "none",
          transition: "all 0.25s ease",
        }}
      />
      <label
        style={{
          position: "absolute",
          left: 12,
          top: active ? 2 : "50%",
          transform: active ? "translateY(0) scale(0.75)" : "translateY(-50%) scale(1)",
          transformOrigin: "left top",
          color: active ? "#00d9ff" : "#8fd9ec99",
          fontSize: 12,
          pointerEvents: "none",
          transition: "all 0.2s ease",
        }}
      >
        {label}
      </label>
    </div>
  );
}
