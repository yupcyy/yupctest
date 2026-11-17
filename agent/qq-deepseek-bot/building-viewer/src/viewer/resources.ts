import {
  BlockDefinition,
  BlockModel,
  Identifier,
  TextureAtlas,
  upperPowerOfTwo,
  type Resources,
} from 'deepslate'

const ROOT = '/mcmeta'
const VERSION = '1.20.1'

async function json(path: string) {
  const response = await fetch(`${ROOT}/${path}`)
  if (!response.ok) throw new Error(`资源加载失败：HTTP ${response.status}`)
  return response.json()
}

async function image(path: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const value = new Image()
    value.onload = () => resolve(value)
    value.onerror = () => reject(new Error('纹理图集加载失败'))
    value.src = `${ROOT}/${path}`
  })
}

export async function loadResources(): Promise<Resources> {
  const [blocks, definitionsJson, modelsJson, uvMap, atlas] = await Promise.all([
    json(`${VERSION}-summary/blocks/data.min.json`),
    json(`${VERSION}-summary/assets/block_definition/data.min.json`),
    json(`${VERSION}-summary/assets/model/data.min.json`),
    json(`${VERSION}-atlas/all/data.min.json`),
    image(`${VERSION}-atlas/all/atlas.png`),
  ])
  const definitions: Record<string, BlockDefinition> = {}
  for (const [id, value] of Object.entries(definitionsJson)) {
    definitions[`minecraft:${id}`] = BlockDefinition.fromJson(value as never)
  }
  const models: Record<string, BlockModel> = {}
  for (const [id, value] of Object.entries(modelsJson)) {
    models[`minecraft:${id}`] = BlockModel.fromJson(value as never)
  }
  const modelProvider = { getBlockModel: (id: Identifier) => models[id.toString()] }
  Object.values(models).forEach(model => model.flatten(modelProvider))

  const size = upperPowerOfTwo(Math.max(atlas.width, atlas.height))
  const canvas = document.createElement('canvas')
  canvas.width = size; canvas.height = size
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) throw new Error('浏览器不支持 Canvas 2D')
  context.drawImage(atlas, 0, 0)
  const mapping: Record<string, [number, number, number, number]> = {}
  for (const [id, value] of Object.entries(uvMap as Record<string, number[]>)) {
    const [u, v, du, dv] = value
    const height = du !== dv && id.startsWith('block/') ? du : dv
    mapping[Identifier.create(id).toString()] = [u / size, v / size, (u + du) / size, (v + height) / size]
  }
  const textures = new TextureAtlas(context.getImageData(0, 0, size, size), mapping)
  const transparent = new Set(['minecraft:glass', 'minecraft:glass_pane', 'minecraft:air', 'minecraft:cave_air'])
  return {
    getBlockDefinition(id) { return definitions[id.toString()] },
    getBlockModel(id) { return models[id.toString()] },
    getTextureUV(id) { return textures.getTextureUV(id) },
    getTextureAtlas() { return textures.getTextureAtlas() },
    getPixelSize() { return textures.getPixelSize() },
    getBlockFlags(id) {
      const name = id.toString()
      return { opaque: !transparent.has(name), semi_transparent: transparent.has(name), self_culling: true }
    },
    getBlockProperties(id) { return blocks[id.path]?.[0] ?? null },
    getDefaultBlockProperties(id) { return blocks[id.path]?.[1] ?? null },
  }
}
