import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, Float } from "@react-three/drei";

// Unique visual identity per role — this palette is NEXUS's signature,
// distinct from generic "AI dashboard" blue/purple defaults.
const ROLE_STYLE = {
  product_manager: { color: "#ff6b35", label: "PM" },
  backend_engineer: { color: "#00d9ff", label: "Backend" },
  frontend_engineer: { color: "#c77dff", label: "Frontend" },
  qa_engineer: { color: "#39ff88", label: "QA" },
  devops_engineer: { color: "#ffd23f", label: "DevOps" },
};

export default function AgentNode({ role, position, active }) {
  const meshRef = useRef();
  const style = ROLE_STYLE[role] ?? { color: "#ffffff", label: role };

  useFrame((state) => {
    if (!meshRef.current) return;
    const pulse = active ? 1 + Math.sin(state.clock.elapsedTime * 6) * 0.15 : 1;
    meshRef.current.scale.setScalar(pulse);
  });

  return (
    <Float speed={active ? 3 : 1} floatIntensity={active ? 1.2 : 0.4}>
      <mesh ref={meshRef} position={position}>
        <icosahedronGeometry args={[0.6, 1]} />
        <meshStandardMaterial
          color={style.color}
          emissive={style.color}
          emissiveIntensity={active ? 1.4 : 0.3}
          wireframe={!active}
        />
        <Html distanceFactor={10} position={[0, -1, 0]}>
          <div
            style={{
              color: style.color,
              fontFamily: "monospace",
              fontSize: "12px",
              fontWeight: 700,
              textShadow: "0 0 8px rgba(0,0,0,0.8)",
              whiteSpace: "nowrap",
            }}
          >
            {style.label} {active ? "● working" : ""}
          </div>
        </Html>
      </mesh>
    </Float>
  );
}
