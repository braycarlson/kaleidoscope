import { afterEach, beforeEach } from 'vitest';
import { config } from '@vue/test-utils';

export const vue_reports: string[] = [];

function vue_warning_report(message: string) {
    vue_reports.push('warning: ' + message);
}

function vue_error_report(error: unknown) {
    vue_reports.push('error: ' + String(error));
}

config.global.config.warnHandler = vue_warning_report;
config.global.config.errorHandler = vue_error_report;

beforeEach(function() {
    vue_reports.length = 0;
});

afterEach(function() {
    if (vue_reports.length === 0) return;

    const reports = vue_reports.join('\n');

    vue_reports.length = 0;

    throw new Error('Vue reported problems during the test:\n' + reports);
});
