<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { TaskProgress } from "../lib/chat";

const props = withDefaults(defineProps<{ progress?: TaskProgress }>(), {
  progress: () => ({ round_id: null, phase: "idle", steps: [] }),
});

const taskBox = ref<HTMLElement | null>(null);
const pinnedToBottom = ref(true);

function onTaskScroll() {
  const el = taskBox.value;
  if (!el) return;
  pinnedToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
}

watch(
  () => props.progress?.steps,
  async () => {
    await nextTick();
    const el = taskBox.value;
    if (!el || !pinnedToBottom.value) return;
    el.scrollTop = el.scrollHeight;
  },
  { deep: true },
);
</script>

<template>
  <aside class="agent-task-rail">
    <section ref="taskBox" class="agent-task-progress" @scroll="onTaskScroll">
      <h3>当前任务</h3>
      <p v-if="!(progress && progress.steps.length)" class="agent-task-empty">暂无进行中的任务</p>
      <ol v-else class="agent-task-steps">
        <li
          v-for="step in progress.steps"
          :key="step.id"
          class="agent-task-step"
          :class="['is-' + step.status, { 'is-spin': step.spin }]"
        >
          <div class="agent-task-row">
            <span v-if="step.spin" class="agent-task-spin" aria-hidden="true"></span>
            <span v-else-if="step.status === 'done'" class="agent-task-check" aria-hidden="true">✓</span>
            <span v-else-if="step.status === 'failed'" class="agent-task-fail" aria-hidden="true">✕</span>
            <span v-else class="agent-task-wait" aria-hidden="true"></span>
            <span class="agent-task-label">{{ step.label }}</span>
          </div>
          <ol v-if="step.children && step.children.length" class="agent-task-children">
            <li
              v-for="child in step.children"
              :key="child.id"
              class="agent-task-step"
              :class="['is-' + child.status, { 'is-spin': child.spin }]"
            >
              <div class="agent-task-row">
                <span v-if="child.spin" class="agent-task-spin" aria-hidden="true"></span>
                <span v-else-if="child.status === 'done'" class="agent-task-check" aria-hidden="true">✓</span>
                <span v-else-if="child.status === 'failed'" class="agent-task-fail" aria-hidden="true">✕</span>
                <span v-else class="agent-task-wait" aria-hidden="true"></span>
                <span class="agent-task-label">{{ child.label }}</span>
              </div>
            </li>
          </ol>
        </li>
      </ol>
    </section>
  </aside>
</template>
