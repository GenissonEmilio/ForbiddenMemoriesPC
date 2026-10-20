// Browser build, run before the program: the user's own disc image as the game's data folder.
// The page sets Module.webDisc = {size, readAt(offset, length) -> Promise<Uint8Array>} (a File the user chose, read
// in place with File.slice; nothing is uploaded) and awaits Module.webDiscIndex() before starting the program.
// The index has the layout port/tools/extract_disc.py makes: gamedata/disc/<path on the disc> for the loose files,
// gamedata/pzs3usN/NNNNN.bin for entry NNNNN of archive DATA/PZS3USN.AFS.

Module.webIndex = null;
Module.webCache = new Map(); // gamedata path -> bytes kept in the in-memory file system (oldest first)
Module.webCacheBytes = 0;
Module.webCacheBudget = Module.webCacheBudget || 768 * 1024 * 1024; // (the page sets less on phones)

Module.webDiscIndex = async function () {
    const disc = Module.webDisc, index = Object.create(null);
    const u32 = (b, o) => b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] * 0x1000000);
    const pvd = await disc.readAt(16 * 2048, 2048);
    if (String.fromCharCode(...pvd.subarray(1, 6)) !== 'CD001') throw new Error('not an ISO 9660 disc image');
    // the directories, from the root (ISO 9660: records of length, extent, size, flags, name)
    const walk = async (lba, size, prefix) => {
        const dir = await disc.readAt(lba * 2048, size);
        for (let o = 0; o < dir.length;) {
            const len = dir[o];
            if (len === 0) { o = (Math.floor(o / 2048) + 1) * 2048; continue; } // records do not cross sectors
            const ext = u32(dir, o + 2), sz = u32(dir, o + 10), flags = dir[o + 25], nl = dir[o + 32];
            const raw = dir.subarray(o + 33, o + 33 + nl);
            o += len;
            if (nl === 1 && (raw[0] === 0 || raw[0] === 1)) continue; // . and ..
            const name = String.fromCharCode(...raw).replace(/;1$/, '');
            if (flags & 2) await walk(ext, sz, prefix + name + '/');
            else index['disc/' + prefix + name] = [ext * 2048, sz];
        }
    };
    await walk(u32(pvd, 156 + 2), u32(pvd, 156 + 10), '');
    if (!index['disc/SLUS_216.78'] || !index['disc/BIN/DBZP.BIN']) {
        throw new Error('this is not Dragon Ball Z: Budokai Tenkaichi 3 (USA, SLUS-21678): no SLUS_216.78 on it');
    }
    // the archives' entries
    let entries = 0;
    for (const n of [0, 1, 2]) {
        const afs = index[`disc/DATA/PZS3US${n}.AFS`];
        if (!afs) throw new Error(`DATA/PZS3US${n}.AFS is missing from the disc image`);
        const head = await disc.readAt(afs[0], 8);
        if (String.fromCharCode(...head.subarray(0, 3)) !== 'AFS') throw new Error(`PZS3US${n}.AFS is not an AFS archive`);
        const count = u32(head, 4), tbl = await disc.readAt(afs[0] + 8, count * 8);
        for (let i = 0; i < count; i++) {
            index[`pzs3us${n}/${String(i).padStart(5, '0')}.bin`] = [afs[0] + u32(tbl, i * 8), u32(tbl, i * 8 + 4)];
        }
        entries += count;
        delete index[`disc/DATA/PZS3US${n}.AFS`]; // as extract_disc.py: the loose entries replace the archive
    }
    Module.webIndex = index;
    return entries;
};

// Called by Web_Fopen (port/web/target/disc_web.c) before a file is opened for reading. 1: there (or not ours).
Module.webDiscEnsure = async function (path) {
    const m = /^\/?gamedata\/(.*)$/.exec(path);
    if (m === null || Module.webIndex === null) return 1;
    const rel = m[1].replace(/\/+/g, '/'), ent = Module.webIndex[rel];
    if (ent === undefined) return 0;
    const full = '/gamedata/' + rel, cache = Module.webCache;
    if (cache.has(full)) { const n = cache.get(full); cache.delete(full); cache.set(full, n); return 1; }
    const bytes = await Module.webDisc.readAt(ent[0], ent[1]);
    FS.mkdirTree(full.slice(0, full.lastIndexOf('/')));
    FS.writeFile(full, bytes);
    cache.set(full, bytes.length);
    Module.webCacheBytes += bytes.length;
    for (const [p, n] of cache) { // oldest first; an open file keeps its data until it is closed
        if (Module.webCacheBytes <= Module.webCacheBudget || p === full) break;
        try { FS.unlink(p); } catch (e) { }
        cache.delete(p);
        Module.webCacheBytes -= n;
    }
    return 1;
};
