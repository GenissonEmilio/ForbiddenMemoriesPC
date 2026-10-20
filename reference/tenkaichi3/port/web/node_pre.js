// Node test build: the game reads its switches from the environment (BT3_DEMO, BT3_GS, ...).
Module.preRun = (Module.preRun || []).concat([() => { for (const k in process.env) ENV[k] = process.env[k]; }]);
