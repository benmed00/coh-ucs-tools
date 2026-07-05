/* Hero 3D: wireframe globe with locale markers + radar sweep (Three.js, CDN).
   Falls back to a pure-CSS radar if WebGL is unavailable. */

const canvas = document.getElementById("hero-canvas");
const fallback = document.getElementById("hero-fallback");

function showFallback() {
  if (canvas) canvas.remove();
  if (fallback) fallback.hidden = false;
}

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext &&
      (c.getContext("webgl2") || c.getContext("webgl")));
  } catch {
    return false;
  }
}

async function boot() {
  if (!canvas || !webglAvailable()) { showFallback(); return; }
  let THREE;
  try {
    THREE = await import("https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js");
  } catch {
    showFallback(); return; // offline / CDN blocked
  }

  const AMBER = 0xffb648, OLIVE = 0x8a9a5b, GREEN = 0x9acd68;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 2, 0.1, 100);
  camera.position.set(0, 1.1, 6.2);
  camera.lookAt(0, 0, 0);

  const rig = new THREE.Group();
  // shift the composition to the right so the hero copy stays readable
  rig.position.x = 1.9;
  scene.add(rig);

  // --- wireframe globe -------------------------------------------------
  const globe = new THREE.Group();
  rig.add(globe);
  const sphereGeo = new THREE.IcosahedronGeometry(1.5, 2);
  globe.add(new THREE.LineSegments(
    new THREE.WireframeGeometry(sphereGeo),
    new THREE.LineBasicMaterial({ color: OLIVE, transparent: true, opacity: 0.42 }),
  ));

  // locale markers: rough lat/lon of localization hotspots
  const locales = [
    [52.5, 13.4],   // Berlin (de)
    [48.9, 2.4],    // Paris (fr)
    [51.5, -0.1],   // London (en-gb)
    [55.8, 37.6],   // Moscow (ru)
    [40.4, -3.7],   // Madrid (es)
    [41.9, 12.5],   // Rome (it)
    [52.2, 21.0],   // Warsaw (pl)
    [39.9, 116.4],  // Beijing (zh)
    [35.7, 139.7],  // Tokyo (ja)
    [37.8, -122.4], // SF (en-us)
  ];
  const markerGeo = new THREE.SphereGeometry(0.035, 8, 8);
  const markerMat = new THREE.MeshBasicMaterial({ color: AMBER });
  for (const [lat, lon] of locales) {
    const phi = (90 - lat) * Math.PI / 180;
    const theta = (lon + 180) * Math.PI / 180;
    const m = new THREE.Mesh(markerGeo, markerMat);
    m.position.setFromSphericalCoords(1.52, phi, theta);
    globe.add(m);
  }

  // --- radar ring + sweep ----------------------------------------------
  const radar = new THREE.Group();
  radar.position.y = -1.75;
  radar.rotation.x = -Math.PI / 2.15;
  rig.add(radar);

  for (const r of [0.9, 1.5, 2.1, 2.7]) {
    const ring = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(
        Array.from({ length: 64 }, (_, i) => {
          const a = (i / 64) * Math.PI * 2;
          return new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0);
        })),
      new THREE.LineBasicMaterial({ color: OLIVE, transparent: true, opacity: 0.28 }),
    );
    radar.add(ring);
  }
  // sweep wedge
  const sweepShape = new THREE.Shape();
  sweepShape.moveTo(0, 0);
  sweepShape.absarc(0, 0, 2.7, 0, Math.PI / 5, false);
  sweepShape.lineTo(0, 0);
  const sweep = new THREE.Mesh(
    new THREE.ShapeGeometry(sweepShape, 24),
    new THREE.MeshBasicMaterial({ color: GREEN, transparent: true, opacity: 0.14, side: THREE.DoubleSide }),
  );
  radar.add(sweep);
  const needle = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(2.7, 0, 0)]),
    new THREE.LineBasicMaterial({ color: GREEN, transparent: true, opacity: 0.7 }),
  );
  sweep.add(needle);

  // --- compass rose (low-poly, flat) -------------------------------------
  const rose = new THREE.Group();
  rose.position.set(-2.6, 0.4, 0.4);
  rose.scale.setScalar(0.55);
  rig.add(rose);
  const roseMat = new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.55 });
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    const len = i % 2 === 0 ? 1.0 : 0.55;
    const tip = new THREE.Vector3(Math.cos(a) * len, Math.sin(a) * len, 0);
    const left = new THREE.Vector3(Math.cos(a + 0.28) * 0.18, Math.sin(a + 0.28) * 0.18, 0);
    const right = new THREE.Vector3(Math.cos(a - 0.28) * 0.18, Math.sin(a - 0.28) * 0.18, 0);
    rose.add(new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints([left, tip, right]), roseMat));
  }

  // --- render loop -------------------------------------------------------
  function resize() {
    const { clientWidth: w, clientHeight: h } = canvas.parentElement;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener("resize", resize);

  let raf = 0;
  const clock = new THREE.Clock();
  function frame() {
    const t = clock.getElapsedTime();
    globe.rotation.y = t * 0.18;
    globe.rotation.x = Math.sin(t * 0.11) * 0.08;
    sweep.rotation.z = -t * 1.1;
    rose.rotation.z = Math.sin(t * 0.4) * 0.15;
    renderer.render(scene, camera);
    raf = requestAnimationFrame(frame);
  }
  frame();

  // save cycles when the tab is hidden
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cancelAnimationFrame(raf);
    else frame();
  });
}

boot();
