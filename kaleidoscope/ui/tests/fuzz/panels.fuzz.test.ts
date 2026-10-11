import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import CachePanel from '../../src/components/panels/CachePanel.vue';
import LineProfilerPanel from '../../src/components/panels/LineProfilerPanel.vue';
import MemoryPanel from '../../src/components/panels/MemoryPanel.vue';
import ProfilingPanel from '../../src/components/panels/ProfilingPanel.vue';
import QueriesPanel from '../../src/components/panels/QueriesPanel.vue';
import RequestPanel from '../../src/components/panels/RequestPanel.vue';
import SettingsPanel from '../../src/components/panels/SettingsPanel.vue';
import SignalsPanel from '../../src/components/panels/SignalsPanel.vue';
import StaticFilesPanel from '../../src/components/panels/StaticFilesPanel.vue';
import TemplatesPanel from '../../src/components/panels/TemplatesPanel.vue';
import TimerPanel from '../../src/components/panels/TimerPanel.vue';
import VersionsPanel from '../../src/components/panels/VersionsPanel.vue';
import {
    CONTRACT,
    TEXT_ARBITRARY,
    contract_arbitrary,
    contract_errors,
    texts_unsafe,
} from '../support/contract';
import { fuzz_runs, fuzz_timeout } from '../support/fuzz';
import { vue_reports } from '../support/setup';

interface Interaction {
    index: number;
    kind: 'click' | 'type';
    text: string;
}

const CLICKABLE = 'button, th, tr, td, span, div.cursor-pointer, [role="switch"]';
const INTERACTIONS_MAX = 8;

const INTERACTION_ARBITRARY = fc.record({
    index: fc.nat({ max: 10_000 }),
    kind: fc.constantFrom('click' as const, 'type' as const),
    text: TEXT_ARBITRARY,
});

const PANELS: Record<string, Component> = Object.freeze({
    cache: CachePanel,
    line_profiling: LineProfilerPanel,
    memory: MemoryPanel,
    profiling: ProfilingPanel,
    queries: QueriesPanel,
    request: RequestPanel,
    settings: SettingsPanel,
    signals: SignalsPanel,
    staticfiles: StaticFilesPanel,
    templates: TemplatesPanel,
    timer: TimerPanel,
    versions: VersionsPanel,
});

async function interactions_run(wrapper: VueWrapper, interactions: Interaction[]): Promise<void> {
    for (const interaction of interactions.slice(0, INTERACTIONS_MAX)) {
        const selector = interaction.kind === 'click' ? CLICKABLE : 'input';
        const targets = wrapper.findAll(selector);
        const target = targets[interaction.index % Math.max(targets.length, 1)];

        if (target === undefined) continue;

        if (interaction.kind === 'click') {
            await target.trigger('click');
        } else {
            await target.setValue(interaction.text);
        }

        await flushPromises();
    }
}

describe('the panel components', function() {
    it('cover exactly the panels of the contract', function() {
        const panel_ids = Object.keys(PANELS).sort();
        const contract_ids = Object.keys(CONTRACT.panels).sort();

        expect(panel_ids).toEqual(contract_ids);
    });

    it.each(Object.keys(PANELS))(
        'render any data the contract allows for %s, survive any interaction, then any other',
        async function(panel_id) {
            const entry = CONTRACT.panels[panel_id];
            const component = PANELS[panel_id];

            if (entry === undefined) throw new Error('the contract has no entry for ' + panel_id);
            if (component === undefined) throw new Error('no component renders ' + panel_id);

            const arbitrary = contract_arbitrary(entry);
            const bounds = { maxLength: INTERACTIONS_MAX };
            const interactions_arbitrary = fc.array(INTERACTION_ARBITRARY, bounds);

            await fc.assert(
                fc.asyncProperty(
                    arbitrary,
                    interactions_arbitrary,
                    arbitrary,
                    async function(first, interactions, second) {
                        expect(contract_errors(entry, first)).toEqual([]);

                        const wrapper = mount(component, { props: { data: first } }) as VueWrapper;
                        const unsafe_first = texts_unsafe(wrapper.element as Element);

                        await interactions_run(wrapper, interactions);

                        const unsafe_interacted = texts_unsafe(wrapper.element as Element);

                        await wrapper.setProps({ data: second });

                        const unsafe_second = texts_unsafe(wrapper.element as Element);
                        const reports = vue_reports.splice(0);

                        wrapper.unmount();

                        expect(reports).toEqual([]);
                        expect(unsafe_first).toEqual([]);
                        expect(unsafe_interacted).toEqual([]);
                        expect(unsafe_second).toEqual([]);
                    },
                ),
                { numRuns: fuzz_runs() },
            );
        },
        fuzz_timeout(),
    );
});
