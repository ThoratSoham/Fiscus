/*
 * Fiscus 3D hero — a stylized brutalist clock tower (Big Ben nod).
 *
 * Built entirely from flat, unlit MeshBasicMaterial boxes and edge
 * wireframes so it keeps the harsh "raw" brutalist look — no soft PBR
 * lighting, no curves. Slow auto-rotate + drag-to-orbit (OrbitControls).
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
  camera.position.set(6.4, 3.4, 8.6);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.minPolarAngle = Math.PI / 4;
  controls.maxPolarAngle = Math.PI / 2.12;
  controls.target.set(0, 3.4, 0);

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

  /* ---- the tower ---- */
  const group = new THREE.Group();

  // plinth
  const plinth = withEdges(box(3.4, 0.7, 3.4, BLUE), BLACK);
  plinth.position.y = 0.35;
  group.add(plinth);

  // shaft
  const shaft1 = withEdges(box(2.2, 2.6, 2.2, WHITE), BLACK);
  shaft1.position.y = 2.0;
  group.add(shaft1);

  const shaft2 = withEdges(box(1.8, 2.2, 1.8, BLUE), BLACK);
  shaft2.position.y = 4.4;
  group.add(shaft2);

  // clock stage
  const stage = withEdges(box(2.7, 1.5, 2.7, BLACK), WHITE);
  stage.position.y = 6.25;
  group.add(stage);

  // clock face (front, +z)
  const face = box(2.0, 1.15, 0.14, WHITE);
  face.position.set(0, 6.25, 1.43);
  group.add(face);

  // clock hands — classic "10:10" look, thin black slabs on the white face
  const hand = (len, angle) => {
    const h = new THREE.Mesh(
      new THREE.BoxGeometry(0.1, len, 0.05),
      new THREE.MeshBasicMaterial({ color: BLACK })
    );
    h.position.set(Math.sin(angle) * len * 0.5, 6.25 + Math.cos(angle) * len * 0.5, 1.49);
    h.rotation.z = angle;
    return h;
  };
  group.add(hand(0.5, -0.95)); // hour
  group.add(hand(0.68, -1.15)); // minute
  const dot = box(0.18, 0.18, 0.05, BLACK);
  dot.position.set(0, 6.25, 1.49);
  group.add(dot);

  // spire
  const spire = new THREE.Mesh(
    new THREE.CylinderGeometry(0.3, 0.9, 2.0, 4),
    new THREE.MeshBasicMaterial({ color: WHITE })
  );
  spire.position.y = 8.0;
  group.add(withEdges(spire, BLACK));

  // orbiting accents — two small blocks circling the shaft
  const orbiters = new THREE.Group();
  const orbA = withEdges(box(0.4, 0.4, 0.4, BLUE), BLACK);
  orbA.position.set(2.9, 0, 0);
  const orbB = withEdges(box(0.32, 0.32, 0.32, WHITE), BLACK);
  orbB.position.set(-2.9, 0, 0);
  orbiters.add(orbA, orbB);
  group.add(orbiters);

  scene.add(group);

  /* ---- loop ---- */
  const clock = new THREE.Clock();

  function tick() {
    requestAnimationFrame(tick);
    if (document.hidden) return; // pause rendering while the tab is hidden

    const dt = clock.getDelta();
    const t = clock.elapsedTime;

    group.rotation.y += dt * 0.25; // slow auto-rotate
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
