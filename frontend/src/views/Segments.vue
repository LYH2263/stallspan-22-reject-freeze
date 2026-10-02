<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const newWidth = ref<number | null>(null)
const busy = ref(false)
const err = ref('')
async function load() { rows.value = await api('/segments') }
async function widen(r: any) {
  busy.value = true; err.value = ''
  try {
    await api(`/segments/${r.id}`, { method: 'PATCH', body: JSON.stringify({ width_m: newWidth.value }) })
    newWidth.value = null
    await load()
  } catch (e: any) { err.value = String(e.message || e) }
  finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <h1>街段</h1>
  <p class="sub">外扩只能加宽；旧运行保留当时宽度快照，并排查看不改口</p>
  <div class="card">
    <table>
      <thead><tr><th>街段</th><th>宽度(m)</th><th>集日ID</th><th>外扩到(m)</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.name }}</td><td>{{ r.width_m }}</td><td>{{ r.market_day_id }}</td>
          <td>
            <input v-model.number="newWidth" type="number" step="0.5" :min="r.width_m" style="width:6rem">
            <button class="btn" style="padding:.2rem .6rem;margin-left:.3rem"
                    :disabled="busy || newWidth == null || newWidth < r.width_m" @click="widen(r)">外扩</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="err" class="badge badge-bad" style="margin-top:.4rem">{{ err }}</p>
  </div>
</template>
