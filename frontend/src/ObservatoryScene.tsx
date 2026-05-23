import { useEffect, useRef } from 'react'
import * as THREE from 'three'

export type ObservatoryPayload = {
  source: string
  truth_label: string
  visual: {
    pose_state: string
    avatar: string
    trust: string
    opacity: number
    claim: string
    reasons: string[]
  }
  persons: {
    range: string
    label: string
    trusted: boolean
  }
  signal: {
    quality: string
    fps: number
    packets: number
    reasons: string[]
  }
  vitals: {
    resp_bpm: number
    heart_bpm: number
    available: boolean
  }
  motion: {
    display_level: string
    state: string
    cadence_spm: number
    trusted: boolean
  }
}

type ObservatorySceneProps = {
  payload: ObservatoryPayload
}

const avatarColorByTrust: Record<string, number> = {
  trusted: 0x57f287,
  weak: 0xf59e0b,
  blocked: 0xf87171,
}

export function ObservatoryScene({ payload }: ObservatorySceneProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) {
      return
    }

    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog(0x08110d, 7, 19)

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100)
    camera.position.set(0.1, 5.7, 9.2)
    camera.lookAt(0, 1.1, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setClearColor(0x050807, 1)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    host.appendChild(renderer.domElement)

    const resize = () => {
      const width = Math.max(320, host.clientWidth)
      const height = Math.max(420, host.clientHeight)
      renderer.setSize(width, height)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }

    const observer = new ResizeObserver(resize)
    observer.observe(host)
    resize()

    scene.add(new THREE.AmbientLight(0x7dd3fc, 0.7))
    const keyLight = new THREE.PointLight(0x9fffb8, 2.2, 12)
    keyLight.position.set(0, 4.8, 2.2)
    scene.add(keyLight)

    addRoom(scene)
    addWifiWaves(scene, payload.signal.quality)
    addSignalField(scene, payload)
    addAvatar(scene, payload)

    let frame = 0
    let animationId = 0
    const animate = () => {
      frame += 1
      scene.rotation.y = Math.sin(frame / 280) * 0.035
      animationId = window.requestAnimationFrame(animate)
      renderer.render(scene, camera)
    }
    animate()

    return () => {
      window.cancelAnimationFrame(animationId)
      observer.disconnect()
      renderer.dispose()
      host.removeChild(renderer.domElement)
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          object.geometry.dispose()
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          materials.forEach((material) => material.dispose())
        }
      })
    }
  }, [payload])

  return <div className="observatory-canvas" ref={hostRef} aria-label="CSI observatory 3D scene" />
}

function addRoom(scene: THREE.Scene) {
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(12, 8),
    new THREE.MeshStandardMaterial({ color: 0x101a12, roughness: 0.82, metalness: 0.08 }),
  )
  floor.rotation.x = -Math.PI / 2
  floor.position.y = -0.02
  scene.add(floor)

  const grid = new THREE.GridHelper(12, 18, 0x1d6cff, 0x123a24)
  grid.position.y = 0.01
  scene.add(grid)

  const router = new THREE.Mesh(
    new THREE.BoxGeometry(0.34, 0.5, 0.2),
    new THREE.MeshStandardMaterial({ color: 0x111827, emissive: 0x2563eb, emissiveIntensity: 0.35 }),
  )
  router.position.set(-3.7, 1.35, -0.9)
  scene.add(router)

  const antenna = new THREE.Mesh(
    new THREE.CylinderGeometry(0.015, 0.015, 0.8, 12),
    new THREE.MeshStandardMaterial({ color: 0x93c5fd, emissive: 0x1d4ed8, emissiveIntensity: 0.4 }),
  )
  antenna.position.set(-3.7, 1.95, -0.9)
  antenna.rotation.z = -0.25
  scene.add(antenna)
}

function addWifiWaves(scene: THREE.Scene, quality: string) {
  const color = quality === 'GOOD' ? 0x2563eb : 0xf59e0b
  for (let i = 0; i < 6; i += 1) {
    const radius = 1.3 + i * 0.75
    const points = []
    for (let step = 0; step <= 84; step += 1) {
      const angle = (step / 84) * Math.PI * 0.92 - Math.PI * 0.46
      points.push(new THREE.Vector3(-3.7 + Math.cos(angle) * radius, 1.25 + Math.sin(angle) * radius, -0.9))
    }
    const wave = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.2 + i * 0.035 }),
    )
    scene.add(wave)
  }
}

function addSignalField(scene: THREE.Scene, payload: ObservatoryPayload) {
  const trusted = payload.visual.trust === 'trusted'
  const baseColor = trusted ? 0x4ade80 : payload.visual.trust === 'weak' ? 0xf59e0b : 0xf87171
  const rows = 7
  const columns = 11
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const wave = Math.sin(row * 0.8 + column * 0.55 + payload.signal.fps * 0.08)
      const height = Math.max(0.02, 0.05 + Math.abs(wave) * (trusted ? 0.18 : 0.08))
      const tile = new THREE.Mesh(
        new THREE.BoxGeometry(0.18, height, 0.18),
        new THREE.MeshStandardMaterial({
          color: baseColor,
          emissive: baseColor,
          emissiveIntensity: trusted ? 0.38 : 0.18,
          transparent: true,
          opacity: trusted ? 0.54 : 0.28,
        }),
      )
      tile.position.set(-4 + column * 0.8, height / 2, -2.8 + row * 0.78)
      scene.add(tile)
    }
  }
}

function addAvatar(scene: THREE.Scene, payload: ObservatoryPayload) {
  if (payload.visual.avatar === 'none') {
    return
  }

  const trustColor = avatarColorByTrust[payload.visual.trust] ?? 0x94a3b8
  const material = new THREE.MeshStandardMaterial({
    color: trustColor,
    emissive: trustColor,
    emissiveIntensity: payload.visual.trust === 'trusted' ? 0.72 : 0.38,
    transparent: true,
    opacity: Math.max(0.18, payload.visual.opacity),
  })
  const jointMaterial = new THREE.MeshStandardMaterial({
    color: 0xff5c5c,
    emissive: 0xff4d4d,
    emissiveIntensity: 0.5,
    transparent: true,
    opacity: Math.max(0.35, payload.visual.opacity),
  })

  const group = new THREE.Group()
  group.position.set(0, 0.08, 0.4)
  scene.add(group)

  const pose = posePoints(payload.visual.pose_state)
  const joints: Record<string, THREE.Vector3> = {}
  Object.entries(pose).forEach(([name, point]) => {
    joints[name] = new THREE.Vector3(point[0], point[1], point[2])
    const joint = new THREE.Mesh(new THREE.SphereGeometry(name === 'head' ? 0.22 : 0.075, 20, 20), jointMaterial)
    joint.position.copy(joints[name])
    group.add(joint)
  })

  const bones: Array<[string, string]> = [
    ['head', 'chest'],
    ['chest', 'pelvis'],
    ['chest', 'leftHand'],
    ['chest', 'rightHand'],
    ['pelvis', 'leftKnee'],
    ['leftKnee', 'leftFoot'],
    ['pelvis', 'rightKnee'],
    ['rightKnee', 'rightFoot'],
  ]
  bones.forEach(([from, to]) => addBone(group, joints[from], joints[to], material))

  if (payload.visual.avatar === 'transparent') {
    const warning = new THREE.Mesh(
      new THREE.TorusGeometry(0.75, 0.02, 12, 80),
      new THREE.MeshBasicMaterial({ color: trustColor, transparent: true, opacity: 0.45 }),
    )
    warning.position.set(0, 0.03, 0)
    warning.rotation.x = Math.PI / 2
    group.add(warning)
  }
}

function addBone(group: THREE.Group, start: THREE.Vector3, end: THREE.Vector3, material: THREE.Material) {
  const distance = start.distanceTo(end)
  const midpoint = start.clone().add(end).multiplyScalar(0.5)
  const bone = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, distance, 14), material)
  bone.position.copy(midpoint)
  bone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), end.clone().sub(start).normalize())
  group.add(bone)
}

function posePoints(state: string): Record<string, [number, number, number]> {
  if (state === 'fallen') {
    return {
      head: [0.72, 0.23, 0],
      chest: [0.28, 0.2, 0],
      pelvis: [-0.22, 0.18, 0],
      leftHand: [0.15, 0.18, -0.45],
      rightHand: [0.16, 0.18, 0.45],
      leftKnee: [-0.62, 0.16, -0.28],
      leftFoot: [-0.96, 0.14, -0.36],
      rightKnee: [-0.62, 0.16, 0.28],
      rightFoot: [-0.96, 0.14, 0.36],
    }
  }

  if (state === 'walking' || state === 'moving') {
    return {
      head: [0, 1.75, 0],
      chest: [0, 1.28, 0],
      pelvis: [0, 0.82, 0],
      leftHand: [-0.42, 0.98, 0.22],
      rightHand: [0.42, 1.48, -0.22],
      leftKnee: [-0.2, 0.42, 0.28],
      leftFoot: [-0.33, 0.05, 0.55],
      rightKnee: [0.2, 0.52, -0.3],
      rightFoot: [0.35, 0.05, -0.58],
    }
  }

  if (state === 'exercise') {
    return {
      head: [0, 1.62, 0],
      chest: [0, 1.12, 0],
      pelvis: [0, 0.68, 0],
      leftHand: [-0.56, 1.62, 0],
      rightHand: [0.56, 1.62, 0],
      leftKnee: [-0.34, 0.34, 0.18],
      leftFoot: [-0.52, 0.05, 0.28],
      rightKnee: [0.34, 0.34, 0.18],
      rightFoot: [0.52, 0.05, 0.28],
    }
  }

  return {
    head: [0, 1.5, 0],
    chest: [0, 1.06, 0],
    pelvis: [0, 0.62, 0],
    leftHand: [-0.44, 0.92, 0],
    rightHand: [0.44, 0.92, 0],
    leftKnee: [-0.24, 0.32, 0.16],
    leftFoot: [-0.42, 0.05, 0.28],
    rightKnee: [0.24, 0.32, 0.16],
    rightFoot: [0.42, 0.05, 0.28],
  }
}
