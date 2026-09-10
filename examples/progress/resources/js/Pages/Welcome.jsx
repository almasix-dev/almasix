export default function Welcome({ framework, package: pkg }) {
  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem" }}>
      <h1>Inertia + {framework}</h1>
      <p>{pkg || "almasix-inertia"}</p>
    </main>
  );
}
