/*
 * Fiscus 3D hero — a stylized brutalist Bombay Stock Exchange.
 *
 * The Dalal Street tower (vertical facade slats + a "market up" ticker
 * arrow) with the iconic charging bull on a plinth at its base. Built
 * entirely from flat, unlit MeshBasicMaterial boxes and edge wireframes
 * so it keeps the harsh "raw" brutalist look — no soft PBR lighting, no
 * curves. Slow auto-rotate + drag-to-orbit (OrbitControls).
 *
 * Mobile / reduced-motion / WebGL-unavailable fallback: the static SVG
 * poster in the template is shown instead.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

(function () {
  "use strict";

  const canvas = document.getElementById("hero-canvas");
  const poster = document.getElementById("hero-poster");
  if (!canvas) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isMobile = window.matchMedia("(max-width: 860px)").matches;
  /* Dev/testing escape hatch: ?force3d=1 renders WebGL even on narrow panes. */
  const force3d = new URLSearchParams(location.search).has("force3d");

  function showPoster() {
    canvas.hidden = true;
    if (poster) poster.hidden = false;
  }

  /* Mobile or reduced motion: skip WebGL entirely, show the static poster. */
  if ((reducedMotion || isMobile) && !force3d) {
    showPoster();
    return;
  }

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch (err) {
    console.warn("Fiscus: WebGL unavailable — falling back to poster.", err);
    showPoster();
    return;
  }

  const BLACK = 0x0b0b0d;
  const WHITE = 0xffffff;
  const BLUE = 0x0038ff;

  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(8.2, 3.6, 10.4);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.minPolarAngle = Math.PI / 4;
  controls.maxPolarAngle = Math.PI / 2.12;
  controls.target.set(0.4, 3.2, 0);

  /* ---- builders ---- */
  function box(w, h, d, color) {
    return new THREE.Mesh(
      new THREE.BoxGeometry(w, h, d),
      new THREE.MeshBasicMaterial({ color })
    );
  }

  function withEdges(mesh, color) {
    const lines = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry),
      new THREE.LineBasicMaterial({ color })
    );
    mesh.add(lines);
    return mesh;
  }

  /* ================= BSE tower ================= */
  const group = new THREE.Group();

  // plinth
  const plinth = withEdges(box(3.2, 0.8, 3.2, BLUE), BLACK);
  plinth.position.y = 0.4;
  group.add(plinth);

  // tower shaft (white) with vertical facade slats (blue) — the BSE look
  const shaft = withEdges(box(2.0, 4.6, 2.0, WHITE), BLACK);
  shaft.position.y = 3.1;
  group.add(shaft);

  for (let i = -2; i <= 2; i++) {
    const slat = withEdges(box(0.12, 3.9, 0.08, BLUE), BLACK);
    slat.position.set(i * 0.3, 3.1, 1.06);
    group.add(slat);
  }

  // crown
  const crown = withEdges(box(1.7, 1.4, 1.7, BLACK), WHITE);
  crown.position.y = 6.1;
  group.add(crown);

  // "market up" ticker: white plaque + blue up-arrow on the crown front
  const plaque = withEdges(box(1.1, 0.55, 0.12, WHITE), BLACK);
  plaque.position.set(0, 6.1, 0.92);
  group.add(plaque);

  const arrowStem = box(0.14, 0.34, 0.08, BLUE);
  arrowStem.position.set(0, 6.1, 0.98);
  group.add(arrowStem);

  const arrowHead = box(0.32, 0.12, 0.08, BLUE);
  arrowHead.position.set(0, 6.1 + 0.23, 0.98);
  group.add(arrowHead);

  // antenna
  const antenna = withEdges(box(0.3, 1.1, 0.3, WHITE), BLACK);
  antenna.position.y = 7.35;
  group.add(antenna);

  /* ================= charging bull ================= */
  const bull = new THREE.Group();

  // pedestal
  const pedestal = withEdges(box(1.7, 0.3, 1.0, WHITE), BLACK);
  pedestal.position.y = 0.15;
  bull.add(pedestal);

  // body
  const body = withEdges(box(1.3, 0.55, 0.55, BLACK), WHITE);
  body.position.set(0, 0.47, 0);
  bull.add(body);

  // legs
  const legPositions = [
    [-0.25, -0.15], [-0.25, 0.15], [0.25, -0.15], [0.25, 0.15],
  ];
  legPositions.forEach(([lx, lz]) => {
    const leg = box(0.12, 0.35, 0.12, BLACK);
    leg.position.set(lx, 0.47 - 0.275 - 0.175, lz);
    bull.add(leg);
  });

  // head (faces +x)
  const head = withEdges(box(0.5, 0.42, 0.46, BLACK), WHITE);
  head.position.set(0.9, 0.47, 0);
  bull.add(head);

  // horns
  const hornPositions = [[0.9, -0.12], [0.9, 0.12]];
  hornPositions.forEach(([hx, hz], i) => {
    const horn = box(0.08, 0.18, 0.08, WHITE);
    horn.position.set(hx, 0.47 + 0.21 + 0.09, hz);
    horn.rotation.z = i === 0 ? -0.55 : 0.55;
    bull.add(horn);
  });

  // tail (sweeps up-back)
  const tail = box(0.07, 0.3, 0.07, BLACK);
  tail.position.set(-0.78, 0.47 + 0.14, 0);
  tail.rotation.z = 0.7;
  bull.add(tail);

  bull.position.set(1.7, 0, 1.5);
  bull.rotation.y = -0.5; // angle the charging bull toward the viewer
  bull.scale.set(1.5, 1.5, 1.5);
  group.add(bull);

  // orbiting accents — two small blocks circling the tower
  const orbiters = new THREE.Group();
  const orbA = withEdges(box(0.4, 0.4, 0.4, BLUE), BLACK);
  orbA.position.set(2.7, 0, 0);
  const orbB = withEdges(box(0.32, 0.32, 0.32, WHITE), BLACK);
  orbB.position.set(-2.7, 0, 0);
  orbiters.add(orbA, orbB);
  group.add(orbiters);

  scene.add(group);

  /* ---- loop ---- */
  const clock = new THREE.Clock();

  function tick() {
    requestAnimationFrame(tick);
    if (document.hidden) return; // pause rendering while the tab is hidden

    const t = clock.elapsedTime;

    /* Gentle sway (not a full spin) so the bull stays facing the viewer;
       drag-to-orbit still gives a full 360° look around the tower. */
    group.rotation.y = Math.sin(t * 0.45) * 0.32;
    group.position.y = Math.sin(t * 0.7) * 0.18; // gentle float
    orbiters.rotation.y = t * 0.6;

    controls.update();
    renderer.render(scene, camera);
  }

  /* ---- sizing ---- */
  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  window.addEventListener("resize", resize);
  resize();
  tick();
})();
