<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { StructureRenderer, type Structure } from 'deepslate'
import { mat4, vec3 } from 'gl-matrix'
import { loadResources } from '../viewer/resources'

const props = defineProps<{ structure: Structure }>()
const canvas = ref<HTMLCanvasElement | null>(null)
const message = ref('正在加载 Minecraft 1.20.1 资源…')
let renderer: StructureRenderer | null = null
let frame = 0
let yaw = .72, pitch = .52, distance = 12
let pan: [number, number] = [0, 0]
let drag: { x: number, y: number, button: number } | null = null
let observer: ResizeObserver | null = null

function draw() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    const target = canvas.value
    if (!target || !renderer) return
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    const width = Math.max(1, Math.floor(target.clientWidth * ratio))
    const height = Math.max(1, Math.floor(target.clientHeight * ratio))
    if (target.width !== width || target.height !== height) {
      target.width = width; target.height = height
      renderer.setViewport(0, 0, width, height)
    }
    const size = props.structure.getSize()
    const view = mat4.create()
    mat4.translate(view, view, [pan[0], pan[1], -distance])
    mat4.rotateX(view, view, pitch)
    mat4.rotateY(view, view, yaw)
    mat4.translate(view, view, [-size[0] / 2, -size[1] / 2, -size[2] / 2])
    renderer.drawGrid(view)
    renderer.drawStructure(view)
  })
}

function down(event: PointerEvent) {
  drag = { x: event.clientX, y: event.clientY, button: event.button }
  canvas.value?.setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (!drag) return
  const dx = event.clientX - drag.x, dy = event.clientY - drag.y
  if (drag.button === 0) {
    yaw += dx / 120
    pitch = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, pitch + dy / 120))
  } else {
    pan = [pan[0] + dx / 80, pan[1] - dy / 80]
  }
  drag = { x: event.clientX, y: event.clientY, button: drag.button }
  draw()
}
function up() { drag = null }
function wheel(event: WheelEvent) {
  event.preventDefault()
  distance = Math.max(2, Math.min(100, distance + event.deltaY / 80))
  draw()
}
function context(event: Event) { event.preventDefault() }

onMounted(async () => {
  try {
    const target = canvas.value
    if (!target) return
    const gl = target.getContext('webgl', { antialias: true })
    if (!gl) throw new Error('浏览器不支持 WebGL')
    renderer = new StructureRenderer(gl, props.structure, await loadResources())
    const size = props.structure.getSize()
    distance = Math.max(6, vec3.length(size) * 1.45)
    message.value = ''
    observer = new ResizeObserver(draw); observer.observe(target)
    draw()
  } catch (cause) {
    message.value = cause instanceof Error ? cause.message : '渲染器初始化失败'
  }
})
watch(() => props.structure, value => {
  renderer?.setStructure(value)
  const size = value.getSize(); distance = Math.max(6, vec3.length(size) * 1.45)
  pan = [0, 0]; draw()
})
onBeforeUnmount(() => { observer?.disconnect(); cancelAnimationFrame(frame) })
</script>

<template>
  <div class="stage">
    <canvas ref="canvas" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @wheel="wheel" @contextmenu="context" />
    <div v-if="message" class="message">{{ message }}</div>
  </div>
</template>

<style scoped>
.stage { position: relative; height: min(68vh, 680px); min-height: 420px; background: radial-gradient(circle at 50% 38%, #243d34, #09120f 72%); }
canvas { display: block; width: 100%; height: 100%; touch-action: none; cursor: grab; }
canvas:active { cursor: grabbing; }
.message { position: absolute; inset: 0; display: grid; place-items: center; color: #a6bdb2; background: #09120fcc; }
@media (max-width: 620px) { .stage { min-height: 360px; } }
</style>
