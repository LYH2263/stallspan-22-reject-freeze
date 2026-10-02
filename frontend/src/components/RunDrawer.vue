<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const props = defineProps<{ currentId?: number | null }>()
const emit = defineEmits<{
  (e: 'select', id: number): void
}>()
const rows = ref<any[]>([])
async function load() {
  rows.value = await api('/allocate/runs?segment_id=1')
}
onMounted(load)
defineExpose({ load })
</script>
<template>
  <div class="card ss-runs">
    <strong>运行抽屉</strong>
    <p class="sub" style="margin:0.25rem 0 0.5rem">摘要逐字取库；几何已漂移或摘要被截短只亮徽标，不改写旧条</p>
    <p v-if="!rows.length" class="muted">尚无已确认运行</p>
    <button
      v-for="r in rows" :key="r.id"
      class="ss-run-row"
      :class="{ 'ss-run-active': r.id === props.currentId }"
      @click="emit('select', r.id)"
    >
      <span class="ss-run-meta">#{{ r.id }} <span v-if="r.created_at" class="muted">{{ r.created_at.replace('T', ' ').slice(0, 19) }}</span></span>
      <span class="ss-run-summary">{{ r.summary || '（无摘要）' }}</span>
      <span class="ss-run-badges">
        <span v-if="r.geometry_drift" class="badge badge-warn">几何已漂移</span>
        <span v-if="r.summary_dirty" class="badge badge-bad">摘要已截短</span>
        <span v-if="!r.geometry_drift && !r.summary_dirty" class="badge badge-ok">固化一致</span>
      </span>
    </button>
  </div>
</template>
<style scoped>
.ss-runs { display: flex; flex-direction: column; gap: 0.35rem; }
.ss-run-row {
  display: grid; grid-template-columns: auto 1fr auto; gap: 0.5rem; align-items: center;
  text-align: left; width: 100%; background: rgba(255,255,255,0.35);
  border: 1px solid var(--ss-curb); border-radius: 3px; padding: 0.4rem 0.55rem;
  cursor: pointer; font-size: 0.8rem; color: var(--ss-ink);
}
.ss-run-row:hover { background: rgba(196,92,38,0.12); }
.ss-run-active { outline: 2px solid var(--ss-accent); }
.ss-run-meta { white-space: nowrap; font-weight: 700; }
.ss-run-summary { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ss-run-badges { display: flex; gap: 0.25rem; white-space: nowrap; }
</style>
