import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, Float, MeshDistortMaterial, Line } from "@react-three/drei";
import * as THREE from "three";

// Unique visual identity per role — a distinct crystal geometry + color per
// specialty instead of five identical spheres, so each agent reads as its
// own instrument in the constellation.
const ROLE_STYLE = {
  product_manager: { color: "#ffb454", label: "Product", geometry: "octahedron" },
  backend_engineer: { color: "#22d3ee", label: "Backend", geometry: "box" },
  frontend_engineer: { color: "#c084fc", label: "Frontend", geometry: "torus" },
  qa_engineer: { color: "#34d399", label: "QA", geometry: "tetrahedron" },
  devops_engineer: { color: "#fb7185", label: "DevOps", geometry: "knot" },
};

function ShapeGeometry({ kind }) {
  switch (kind) {
    case "box":
      return <boxGeometry args={[0.85, 0.85, 0.85]} />;
    case "torus":
      return <torusGeometry args={[0.55, 0.22, 24, 48]} />;
    case "tetrahedron":
      return <tetrahedronGeometry args={[0.75, 0]} />;
    case "knot":
      return <torusKnotGeometry args={[0.42, 0.15, 100, 16]} />;
    case "octahedron":
    default:
      return <octahedronGeometry args={[0.7, 0]} />;
  }
}

// A short pulse of light that travels from the core out to an agent while
// it's actively working — reads as "the task is flowing to this agent".
function EnergyPulse({ from, to, color }) {
  const ref = useRef();
  useFrame((state) => {
    if (!ref.current) return;
    const t = (state.clock.elapsedTime * 0.9) % 1;
    ref.current.position.lerpVectors(new THREE.Vector3(...from), new THREE.Vector3(...to), t);
    const s = 0.08 * (1 - Math.abs(t - 0.5) * 1.4);
    ref.current.scale.setScalar(Math.max(s, 0.02));
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial color={color} toneMapped={false} />
    </mesh>
  );
}

// The static tether connecting an agent to the shared core, always visible
// but dimmer than the active pulse riding along it.
export function ConnectionBeam({ from, to, color, active }) {
  const points = [new THREE.Vector3(...from), new THREE.Vector3(...to)];
  return (
    <>
      <Line points={points} color={color} transparent opacity={active ? 0.55 : 0.16} lineWidth={active ? 1.4 : 0.8} />
      {active && <EnergyPulse from={from} to={to} color={color} />}
    </>
  );
}

// The central intelligence node all agents orbit and report to.
export function CoreNode({ busy }) {
  const meshRef = useRef();
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (meshRef.current) {
      meshRef.current.rotation.y = t * 0.2;
      meshRef.current.rotation.x = Math.sin(t * 0.15) * 0.15;
      const s = 1 + Math.sin(t * (busy ? 3 : 1)) * (busy ? 0.08 : 0.03);
      meshRef.current.scale.setScalar(s);
    }
  });
  return (
    <Float speed={1.4} rotationIntensity={0.3} floatIntensity={0.6}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[0.85, 3]} />
        <MeshDistortMaterial
          color="#7dd3fc"
          emissive="#38bdf8"
          emissiveIntensity={busy ? 0.9 : 0.45}
          distort={busy ? 0.35 : 0.15}
          speed={busy ? 3 : 1}
          roughness={0.2}
          metalness={0.5}
        />
      </mesh>
      <Html distanceFactor={10} position={[0, -1.15, 0]}>
        <div
          style={{
            color: "#bae6fd",
            fontFamily: "'Space Grotesk', monospace",
            fontSize: "11px",
            fontWeight: 700,
            letterSpacing: 1.5,
            textShadow: "0 0 10px #38bdf8cc",
            whiteSpace: "nowrap",
          }}
        >
          NEXUS CORE
        </div>
      </Html>
    </Float>
  );
}

export default function AgentNode({ role, position, active }) {
  const meshRef = useRef();
  const style = ROLE_STYLE[role] ?? { color: "#ffffff", label: role, geometry: "octahedron" };

  useFrame((state) => {
    if (!meshRef.current) return;
    meshRef.current.rotation.y += active ? 0.018 : 0.004;
    meshRef.current.rotation.x += active ? 0.012 : 0.002;
    const pulse = active ? 1 + Math.sin(state.clock.elapsedTime * 5) * 0.12 : 1;
    meshRef.current.scale.setScalar(pulse);
  });

  return (
    <Float speed={active ? 2.6 : 1.1} rotationIntensity={active ? 0.7 : 0.25} floatIntensity={active ? 1.3 : 0.55}>
      <group position={position}>
        <mesh ref={meshRef}>
          <ShapeGeometry kind={style.geometry} />
          <MeshDistortMaterial
            color={style.color}
            emissive={style.color}
            emissiveIntensity={active ? 1.1 : 0.35}
            distort={active ? 0.25 : 0.08}
            speed={active ? 2.5 : 0.6}
            roughness={0.25}
            metalness={0.35}
          />
        </mesh>
        <Html distanceFactor={10} position={[0, -1, 0]}>
          <div
            style={{
              color: style.color,
              fontFamily: "'Space Grotesk', monospace",
              fontSize: "12px",
              fontWeight: 700,
              textShadow: "0 0 10px rgba(0,0,0,0.85)",
              whiteSpace: "nowrap",
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: style.color,
                boxShadow: active ? `0 0 8px ${style.color}` : "none",
                opacity: active ? 1 : 0.5,
              }}
            />
            {style.label}
            {active ? " · working" : ""}
          </div>
        </Html>
      </group>
    </Float>
  );
}
