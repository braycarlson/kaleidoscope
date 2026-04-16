import type { Component } from 'vue';

export type KaleidoscopeState = 'collapsed' | 'strip' | 'panel';

export type SortDirection = 'asc' | 'desc';

export type CopyFormat = 'table' | 'json' | 'text';

export type CopyValue = string | object;

export type KaleidoscopeSide = 'left' | 'right';

export interface PanelMeta {
    id: string;
    isolate: boolean;
    title: string;
    summary: string;
    enabled: boolean;
}

export type PanelRegistry = Record<string, Component>;

export interface StackFrame {
    file: string;
    function: string;
    line: number;
    text: string;
}

export interface QuerySortState {
    column: string;
    direction: SortDirection;
}
