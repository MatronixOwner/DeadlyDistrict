// Распаковка анимаций Mesh2Motion (сжаты EXT_meshopt_compression) в обычные GLB.
// Нужен только при пересборке моделей (см. tools/import_models.py):
//   npm install @gltf-transform/core @gltf-transform/extensions meshoptimizer
//   node tools/m2m_decode.mjs <папка с animations/*.glb> <куда> имя1 имя2 ...
import { NodeIO } from '@gltf-transform/core';
import { EXTMeshoptCompression } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';
import fs from 'node:fs';
import path from 'node:path';

const [src, dst, ...names] = process.argv.slice(2);
await MeshoptDecoder.ready;
const io = new NodeIO().registerExtensions([EXTMeshoptCompression]).registerDependencies({ 'meshopt.decoder': MeshoptDecoder });
fs.mkdirSync(dst, { recursive: true });
for (const name of names) {
  const doc = await io.read(path.join(src, name + '.glb'));
  for (const ext of doc.getRoot().listExtensionsUsed()) {
    if (ext.extensionName === 'EXT_meshopt_compression') ext.dispose();
  }
  await io.write(path.join(dst, name + '.glb'), doc);
}
console.log('decoded', names.length);
