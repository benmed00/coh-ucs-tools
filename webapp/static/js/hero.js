/* Hero 3D: wireframe globe with locale markers + radar sweep (Three.js, CDN).
   Falls back to a pure-CSS radar if WebGL is unavailable. */

const canvas = document.getElementById("hero-canvas");
const fallback = document.getElementById("hero-fallback");

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

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

  const reduced = prefersReducedMotion();
  const AMBER = 0xffb648, OLIVE = 0x8a9a5b, GREEN = 0x9acd68;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 2, 0.1, 100);
  camera.position.set(0, 1.1, 6.2);
  camera.lookAt(0, 0, 0);
  const cameraBaseX = camera.position.x;

  const rig = new THREE.Group();
  rig.position.x = 1.9;
  scene.add(rig);

  const globe = new THREE.Group();
  rig.add(globe);
  const sphereGeo = new THREE.IcosahedronGeometry(1.5, 2);
  const wireMat = new THREE.LineBasicMaterial({ color: OLIVE, transparent: true, opacity: 0.42 });
  globe.add(new THREE.LineSegments(new THREE.WireframeGeometry(sphereGeo), wireMat));

  const locales = [
    ["DE", 52.5, 13.4], ["FR", 48.9, 2.4], ["EN", 51.5, -0.1],
    ["RU", 55.8, 37.6], ["ES", 40.4, -3.7], ["AR", 24.7, 46.7],
    ["PL", 52.2, 21.0], ["CN", 39.9, 116.4], ["JP", 35.7, 139.7],
    ["US", 37.8, -122.4],
  ];
  const markerGeo = new THREE.SphereGeometry(0.04, 8, 8);
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const markers = [];
  for (let i = 0; i < locales.length; i++) {
    const [code, lat, lon] = locales[i];
    const phi = (90 - lat) * Math.PI / 180;
    const theta = (lon + 180) * Math.PI / 180;
    const mat = new THREE.MeshBasicMaterial({ color: AMBER });
    const m = new THREE.Mesh(markerGeo, mat);
    m.position.setFromSphericalCoords(1.52, phi, theta);
    m.userData = { code, phase: i * 0.7 };
    globe.add(m);
    markers.push(m);
  }
  canvas.style.cursor = "grab";
  let hoveredMarker = null;
  function pickMarker(ev) {
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObjects(markers)[0]?.object ?? null;
  }
  canvas.addEventListener("mousemove", (ev) => {
    const hit = pickMarker(ev);
    if (hoveredMarker && hoveredMarker !== hit) {
      hoveredMarker.material.color.setHex(AMBER);
    }
    hoveredMarker = hit;
    if (hoveredMarker) {
      hoveredMarker.material.color.setHex(0xffe0a0);
      canvas.style.cursor = "pointer";
    } else {
      canvas.style.cursor = "grab";
    }
  });
  canvas.addEventListener("mouseleave", () => {
    if (hoveredMarker) hoveredMarker.material.color.setHex(AMBER);
    hoveredMarker = null;
    canvas.style.cursor = "grab";
  });
  canvas.addEventListener("click", (ev) => {
    const hit = pickMarker(ev);
    if (hit) {
      window.dispatchEvent(new CustomEvent("coh-locale-click", { detail: hit.userData.code }));
    }
  });

  const radar = new THREE.Group();
  radar.position.y = -1.75;
  radar.rotation.x = -Math.PI / 2.15;
  rig.add(radar);

  for (const r of [0.9, 1.5, 2.1, 2.7]) {
    radar.add(new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(
        Array.from({ length: 64 }, (_, i) => {
          const a = (i / 64) * Math.PI * 2;
          return new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0);
        })),
      new THREE.LineBasicMaterial({ color: OLIVE, transparent: true, opacity: 0.28 }),
    ));
  }
  const sweepShape = new THREE.Shape();
  sweepShape.moveTo(0, 0);
  sweepShape.absarc(0, 0, 2.7, 0, Math.PI / 5, false);
  sweepShape.lineTo(0, 0);
  const sweep = new THREE.Mesh(
    new THREE.ShapeGeometry(sweepShape, 24),
    new THREE.MeshBasicMaterial({ color: GREEN, transparent: true, opacity: 0.14, side: THREE.DoubleSide }),
  );
  radar.add(sweep);
  sweep.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(2.7, 0, 0)]),
    new THREE.LineBasicMaterial({ color: GREEN, transparent: true, opacity: 0.7 }),
  ));

  const blips = [];
  const blipGeo = new THREE.CircleGeometry(0.08, 12);
  for (let i = 0; i < 4; i++) {
    const blip = new THREE.Mesh(blipGeo, new THREE.MeshBasicMaterial({
      color: GREEN, transparent: true, opacity: 0, side: THREE.DoubleSide,
    }));
    blip.position.set((Math.random() - 0.5) * 4, (Math.random() - 0.5) * 4, 0.01);
    blip.userData = { life: 0 };
    radar.add(blip);
    blips.push(blip);
  }
  let lastSweepAngle = 0;

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
    if (!reduced) {
      globe.rotation.y = t * 0.18;
      globe.rotation.x = Math.sin(t * 0.11) * 0.08;
      sweep.rotation.z = -t * 1.1;
      rose.rotation.z = Math.sin(t * 0.4) * 0.15;
      wireMat.opacity = 0.36 + Math.sin(t * 0.9) * 0.08;
      camera.position.x = cameraBaseX + Math.sin(t * 0.15) * 0.15;
      for (const m of markers) {
        const pulse = 1 + Math.sin(t * 2 + m.userData.phase) * 0.15;
        m.scale.setScalar(pulse);
      }
      const sweepAngle = sweep.rotation.z;
      if (Math.abs(sweepAngle - lastSweepAngle) > 0.4) {
        lastSweepAngle = sweepAngle;
        const blip = blips[Math.floor(Math.random() * blips.length)];
        blip.position.set((Math.random() - 0.5) * 4.5, (Math.random() - 0.5) * 4.5, 0.01);
        blip.userData.life = 1;
      }
      for (const blip of blips) {
        if (blip.userData.life > 0) {
          blip.userData.life -= 0.02;
          blip.material.opacity = blip.userData.life * 0.55;
        }
      }
    } else {
      globe.rotation.y = t * 0.05;
    }
    renderer.render(scene, camera);
    raf = requestAnimationFrame(frame);
  }
  frame();

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cancelAnimationFrame(raf);
    else frame();
  });
}

boot();
