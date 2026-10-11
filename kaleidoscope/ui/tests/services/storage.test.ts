import { describe, expect, it } from 'vitest';
import { storage_read, storage_write } from '../../src/services/storage';

describe('storage keys', function() {
    it('refuses an empty key for a read or a write', function() {
        expect(function() { return storage_read(''); }).toThrow(RangeError);
        expect(function() { return storage_write('', 'value'); }).toThrow(RangeError);
    });
});
