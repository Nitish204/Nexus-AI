import { useEffect, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sparkles, Environment } from "@react-three/drei";

/**
 * The animated 3D background on the sign-in screen — floating,
 * mouse-reactive gems orbiting a central distorted icosahedron.
 *
 * Split out of AuthPage.jsx on purpose: this is the file that pulls in
 * three.js + @react-three/fiber + @react-three/drei, which together
 * were the actual source of the frontend's oversized single JS chunk.
 * AuthPage.jsx now imports this via React.lazy(), so the sign-in form
 * itself paints instantly and this decorative scene streams in a beat
 * later instead of blocking first paint for every visitor.
 */

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

export default function AuthScene() {
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
