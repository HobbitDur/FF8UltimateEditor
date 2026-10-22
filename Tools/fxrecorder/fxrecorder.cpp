// fxrecorder - records what an FF8 battle effect draws, by running the effect's ORIGINAL code.
//
// Fujin's Native preview (Fujin/nativepreview.py) runs this, then draws the recording with its
// software PlayStation GPU (FF8GameData/psxgpu). Derived from the FFNx battle-effect harness
// (fxaudit, D:/FFNxMenu30fps/harness) without its FFNx parts: no ports, no held frames, no A/B
// verification - the game's own executor and code only.
//
// How: the parent process starts itself again as a suspended 32-bit child and reserves 0x400000 in
// it; the child maps FF8_EN.exe there (sections copied, nothing of the exe's startup runs), stubs
// the engine calls with external side effects (sound, file streaming, damage, camera animation,
// VRAM uploads, pad), builds a fake battle (7 entities, a cast context at the real global
// 0x1D99A78, one action), then starts the effect like the game:
//   Magic_GetIDLoad(effect) 0x50AF20 -> setup function -> root queue C3_28 (0x1D96AAC),
// and each tick runs the game's ExecuteTaskQueue (0x508420) on it, until the queue ends.
//
// Output (the "between" format of the harness, read by FF8GameData/psxgpu/fxdump.py):
//   R t n                         tick t, then its n OT insertions:
//   P 0 0 0 0 0 0 0 fn bucket len words...   one GPU packet (hex)
//   C t ex ey ez ax ay az         the battle camera words after the tick (eye, look-at)
//   V t x y w h hexwords          a VRAM upload (queued by the tick, or done before it)
//   B t x y w h u v               a VRAM-to-VRAM copy
//
// Arguments: <effect id> exe=FF8_EN.exe magic=<folder of the mag files> battle=<folder of the battle
// files> out=<file> [model=N: every slot gets c0mN.dat (default 0; -1 = no model)] [ticks=N]
// [targets=N] [caster=slot] [seed=N] [camera=<file>: per tick "t ex ey ez ax ay az roll H" - the
// view the camera player would show, set before the tick; without it a fixed default view]
//
// Build (32-bit, the exe's code runs in this process): Tools/fxrecorder/build.bat.
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <vector>
#include <string>
#include <map>

// ---------------------------------------------------------------- options
struct Opt
{
	int eff = 0, ticks = 3000, targets = 1, caster = 0, model = 0;
	uint32_t seed = 12345;
	std::string exe, magic, battle, out, camera;
};
static Opt O;
static FILE *g_out = nullptr;

static std::vector<uint8_t> readfile(const std::string &p)
{
	std::vector<uint8_t> v;
	FILE *f = fopen(p.c_str(), "rb");
	if (!f) return v;
	fseek(f, 0, SEEK_END);
	long n = ftell(f);
	fseek(f, 0, SEEK_SET);
	if (n > 0) { v.resize(n); fread(v.data(), 1, n, f); }
	fclose(f);
	return v;
}
static std::string join(const std::string &dir, const std::string &name)
{
	if (dir.empty()) return name;
	char last = dir[dir.size() - 1];
	return (last == '/' || last == '\\') ? dir + name : dir + "/" + name;
}

// ---------------------------------------------------------------- VRAM recording
static void dump_rect(int t, const int16_t *rect, const uint16_t *data)
{
	int w = rect[2], h = rect[3];
	if (!g_out || w <= 0 || h <= 0 || w > 1024 || h > 512 || IsBadReadPtr(data, (size_t)w * h * 2)) return;
	fprintf(g_out, "V %d %d %d %d %d ", t, rect[0], rect[1], w, h);
	for (int i = 0; i < w * h; i++) fprintf(g_out, "%04X", data[i]);
	fprintf(g_out, "\n");
}
// a TIM as Battle_FlushVramCommandQueue (0x505D20) uploads it: its CLUT block, then its image block
static void dump_tim(int t, const uint8_t *tim)
{
	if (IsBadReadPtr(tim, 24)) return;
	uint32_t len = *(const uint32_t *)(tim + 8);
	dump_rect(t, (const int16_t *)(tim + 12), (const uint16_t *)(tim + 20));
	if (!IsBadReadPtr(tim + len + 12, 8)) dump_rect(t, (const int16_t *)(tim + len + 12), (const uint16_t *)(tim + len + 20));
}
static int g_tick = 0; // the tick the uploads belong to (0 before the first)
// the battle VRAM command queue (g_command_bffer 0x1D98220, 32 x 16 bytes, count 0x1D98420)
static void dump_vram_queue()
{
	int n = *(int32_t *)0x1D98420;
	if (n > 31) n = 31;
	for (int i = 0; i < n; i++)
	{
		const uint8_t *e = (const uint8_t *)0x1D98220 + 16 * i;
		const int16_t *rect = (const int16_t *)(e + 4);
		uint32_t src = *(const uint32_t *)(e + 12);
		if (e[0] == 0) dump_rect(g_tick, rect, (const uint16_t *)src);
		else if (e[0] == 1) dump_tim(g_tick, (const uint8_t *)src);
		else if (e[0] == 3 && g_out) fprintf(g_out, "B %d %d %d %d %d %u %u\n", g_tick, rect[0], rect[1], rect[2], rect[3], src & 0xFFFF, src >> 16);
	}
	*(uint32_t *)0x1D98420 = 0;
}

// ---------------------------------------------------------------- stubs
struct Pending { int kind; uint32_t a, b, c; };
static std::vector<Pending> g_pending;

static uint8_t g_ptd[0x100];
static uint8_t *__cdecl my_getptd() { return g_ptd; }
static int __cdecl my_rand()
{
	uint32_t &s = *(uint32_t *)(g_ptd + 0x14);
	s = s * 0x343FD + 0x269EC3;
	return (s >> 16) & 0x7FFF;
}
// Magic_LoadTexture_IO_GetsFile (0x571900): name -> <magic folder>/<name>
static uint32_t __cdecl s_loadtex(const char *name, uint8_t *dst, uint32_t max, uint32_t *psize)
{
	std::vector<uint8_t> v = readfile(join(O.magic, name));
	if (v.empty()) { printf("load %s failed\n", name); return 0; }
	if (!dst)
	{
		// dst == 0: the original allocates size + max bytes and records the block in its table
		// 0x21DFAC0 (count 0x21DFABC); the block comes from a fixed arena here
		static uint8_t *arena = nullptr; static uint32_t used = 0;
		if (!arena) arena = (uint8_t *)VirtualAlloc((void *)0x30000000, 0x1000000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
		int32_t &cnt = *(int32_t *)0x21DFABC;
		if (cnt >= 0x100 || !arena) return 0;
		uint32_t sz = (uint32_t)v.size() + max;
		if (used + sz > 0x1000000) return 0;
		dst = arena + used; used += (sz + 15) & ~15u;
		memset(dst, 0, sz);
		((uint8_t **)0x21DFAC0)[cnt++] = dst;
		memcpy(dst, v.data(), v.size());
		if (psize) *psize = (uint32_t)v.size();
		return (uint32_t)dst;
	}
	if (v.size() > max) { printf("load %s too big\n", name); return 0; }
	memcpy(dst, v.data(), v.size());
	if (psize) *psize = (uint32_t)v.size();
	return (uint32_t)dst;
}
static int __cdecl s_zero1(uint32_t) { return 0; }
static int __cdecl s_zero2(uint32_t, uint32_t) { return 0; }
static int __cdecl s_zero3(uint32_t, uint32_t, uint32_t) { return 0; }
static int __cdecl s_zero0() { return 0; }
static int __cdecl s_46BB40(uint32_t, uint32_t) { return 1; }
static int __cdecl s_501860(uint32_t a, uint32_t b) { g_pending.push_back({ 1, a, b, 0 }); return 0; }
static int __cdecl s_48D0A0(uint32_t id, uint32_t dst, uint32_t, uint32_t cb) { g_pending.push_back({ 2, id, dst, cb }); return 0; }
static int __cdecl s_508480(uint32_t a, uint32_t b) { g_pending.push_back({ 2, a, b, 0 }); return 0; }
static int __cdecl s_4A29A0(uint32_t, uint32_t b, uint32_t) { return 0x100 + (int)b; }
static int __cdecl s_508630(uint32_t a, uint32_t b) { *(uint8_t *)b = 0; g_pending.push_back({ 3, a, b, 0 }); return 0; }
static uint32_t __cdecl s_5088A0(uint32_t, uint32_t, uint32_t, uint32_t d) { return d; }
// Battle_QueueVramUpload_Type0_RectData (0x505DF0): recorded at once (model textures, palettes)
static int __cdecl s_505DF0(const int16_t *rect, const uint16_t *data) { if (rect) dump_rect(g_tick, rect, data); return 0; }
// QueueBlitCommand (0x505EB0): a VRAM-to-VRAM copy, recorded
static int __cdecl s_505EB0(const int16_t *r, uint32_t u, uint32_t v)
{
	if (r && g_out) fprintf(g_out, "B %d %d %d %d %d %u %u\n", g_tick, r[0], r[1], r[2], r[3], u & 0xFFFF, v & 0xFFFF);
	return 0;
}
static int __cdecl s_40A0F0(uint32_t, uint32_t, uint32_t) { return 0; } // free_mem_with_line
// pad input (Scan pages its text and waits for a confirm): the harness's default schedule
static int g_cur_tick_pad = 0;
static uint32_t sched_value(const char *s)
{
	uint32_t v = 0;
	std::string text = s; size_t i = 0;
	while (i < text.size())
	{
		size_t j = text.find(',', i); if (j == std::string::npos) j = text.size();
		std::string e = text.substr(i, j - i); size_t at = e.find('@');
		if (at != std::string::npos && atoi(e.c_str() + at + 1) <= g_cur_tick_pad) v = strtoul(e.substr(0, at).c_str(), nullptr, 16);
		i = j + 1;
	}
	return v;
}
static uint32_t __cdecl s_49ED30(uint32_t, uint32_t) { return 0; }
static uint32_t __cdecl s_4A2D60(uint32_t)
{
	return sched_value("0@0,1000@78,1001@80,4004@82,8000@84,2008@86,4001@88,8004@89,2002@90,0@91,5@93,0@94,20@96,0@98,20@100,0@102,40@110");
}
static int32_t __cdecl s_49F0A0(uint32_t, uint32_t, uint32_t) { return (int16_t)sched_value("ffff@0,20@91,c0@92,90@94,60@95,ffff@96"); }

// ---------------------------------------------------------------- patches
struct Patch { uint32_t at; uint8_t orig[5], jmp[5]; };
static Patch g_patches[96];
static int g_npatches = 0;
static Patch *find_patch(uint32_t at) { for (int i = 0; i < g_npatches; i++) if (g_patches[i].at == at) return &g_patches[i]; return nullptr; }
static void unpatch(uint32_t at) { memcpy((void *)at, find_patch(at)->orig, 5); }
static void repatch(uint32_t at) { memcpy((void *)at, find_patch(at)->jmp, 5); }
static void patch_jmp(uint32_t at, void *to)
{
	uint8_t *p = (uint8_t *)at;
	Patch &pt = g_patches[g_npatches < 96 ? g_npatches++ : 95];
	pt.at = at;
	memcpy(pt.orig, p, 5);
	p[0] = 0xE9;
	*(int32_t *)(p + 1) = (int32_t)((uint32_t)to - (at + 5));
	memcpy(pt.jmp, p, 5);
}
static DWORD g_fault_eip, g_fault_addr, g_fault_code;
static int filter(EXCEPTION_POINTERS *e)
{
	g_fault_code = e->ExceptionRecord->ExceptionCode;
	g_fault_eip = e->ContextRecord->Eip;
	g_fault_addr = e->ExceptionRecord->NumberParameters > 1 ? (DWORD)e->ExceptionRecord->ExceptionInformation[1] : 0;
	return EXCEPTION_EXECUTE_HANDLER;
}
// engine functions that run for real but may fault on the fake battle's data: guarded
#define GUARDED(ADDR, CALL, FALLBACK) \
	unpatch(ADDR); uint32_t r; \
	__try { r = (uint32_t)(CALL); } __except (filter(GetExceptionInformation())) { r = (uint32_t)(FALLBACK); } \
	repatch(ADDR); return r;
static uint32_t __cdecl s_5099D0(uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e)
{ GUARDED(0x5099D0, ((uint32_t (__cdecl *)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t))0x5099D0)(a, b, c, d, e), e) }
static uint32_t __cdecl s_508C90(uint32_t a) { GUARDED(0x508C90, ((int (__cdecl *)(uint32_t))0x508C90)(a), 0) }
static uint32_t __cdecl s_5095B0(uint32_t a, uint32_t b) { GUARDED(0x5095B0, ((int (__cdecl *)(uint32_t, uint32_t))0x5095B0)(a, b), 0) }
static uint32_t __cdecl s_508F90(uint32_t a, uint32_t b) { GUARDED(0x508F90, ((int (__cdecl *)(uint32_t, uint32_t))0x508F90)(a, b), 0) }
static uint32_t __cdecl s_509440(uint32_t a, uint32_t b, uint32_t c) { GUARDED(0x509440, ((int (__cdecl *)(uint32_t, uint32_t, uint32_t))0x509440)(a, b, c), 0) }

// ---------------------------------------------------------------- OT insertions = what is drawn
// SSIGPU_InsertPrimNoDepth 0x45C740 / AutoDepth 0x45C7A0 / DepthKeys 0x45C870 / AltViewport 0x45C8E0:
// arg1 = OT bucket, arg2 = packet. The packet words are read after the tick (renderers set the
// length / tpage after inserting).
struct Ins { uint32_t fn, bucket, pkt; };
static std::vector<Ins> g_ins;
static bool g_rec = false;
static void note_ins(uint32_t fn, uint32_t bucket, uint32_t packet) { if (g_rec) g_ins.push_back({ fn, bucket, packet }); }
#define INS_WRAP(ADDR, ...) unpatch(ADDR); ((void (__cdecl *)(__VA_ARGS__))ADDR)
static void __cdecl s_45C740(uint32_t a, uint32_t b, uint32_t c) { INS_WRAP(0x45C740, uint32_t, uint32_t, uint32_t)(a, b, c); repatch(0x45C740); note_ins(0x45C740, a, b); }
static void __cdecl s_45C7A0(uint32_t a, uint32_t b) { INS_WRAP(0x45C7A0, uint32_t, uint32_t)(a, b); repatch(0x45C7A0); note_ins(0x45C7A0, a, b); }
static void __cdecl s_45C870(uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e, uint32_t f)
{ INS_WRAP(0x45C870, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t)(a, b, c, d, e, f); repatch(0x45C870); note_ins(0x45C870, a, b); }
static void __cdecl s_45C8E0(uint32_t a, uint32_t b) { INS_WRAP(0x45C8E0, uint32_t, uint32_t)(a, b); repatch(0x45C8E0); note_ins(0x45C8E0, a, b); }
static void write_tick(int t)
{
	if (!g_out) return;
	fprintf(g_out, "R %d %u\n", t, (unsigned)g_ins.size());
	for (const Ins &r : g_ins)
	{
		if (IsBadReadPtr((void *)r.pkt, 4)) continue;
		uint32_t len = *(const uint8_t *)(r.pkt + 3);
		if (IsBadReadPtr((void *)(r.pkt + 4), len * 4)) continue;
		fprintf(g_out, "P 0 0 0 0 0 0 0 %X %X %u", r.fn, r.bucket, len);
		for (uint32_t k = 0; k < len; k++) fprintf(g_out, " %X", *(const uint32_t *)(r.pkt + 4 + 4 * k));
		fprintf(g_out, "\n");
	}
	const int16_t *eye = (const int16_t *)0xB8B7F0, *at = (const int16_t *)0xB8B7F8;
	fprintf(g_out, "C %d %d %d %d %d %d %d\n", t, eye[0], eye[1], eye[2], at[0], at[1], at[2]);
}

// ---------------------------------------------------------------- battle memory
static uint8_t *g_ot, *g_pkt, *g_scr, *g_fake, *g_modelmem;
static const uint32_t OT_SIZE = 0x20000, PKT_SIZE = 0x400000, SCR_SIZE = 0x40000, FAKE_SIZE = 0x40000;
static const uint32_t MODELMEM_SIZE = 0x400000, MODELWORK_SIZE = 0x40000;
static const uint32_t C3_28 = 0x1D96AAC; // running effect root queue

static void env_reset()
{
	*(uint32_t *)0x1CA8828 = 0x1C48828;       // SSIGPU prim pool cursor
	memset(g_ot, 0, OT_SIZE);
	*(uint32_t *)0x1D8E04C = (uint32_t)g_ot;   // g_Battle_FrameRenderListBase
	*(uint32_t *)0x1D8E054 = (uint32_t)g_pkt;  // frame packet cursor
	*(uint32_t *)0x1D969A8 = (uint32_t)g_pkt + PKT_SIZE;
	*(uint32_t *)0x1D999C4 = (uint32_t)g_scr;  // Field_Alloc stack
}

static void apply_pending(std::vector<Pending> v)
{
	g_pending.clear();
	for (size_t i = 0; i < v.size(); i++)
	{
		const Pending p = v[i];
		if (p.kind == 1) *(uint8_t *)p.b = 1;          // stream ready flag
		else if (p.kind == 3) *(uint8_t *)p.b = 0xFF;  // texture restore done
		else if (p.kind == 2)
		{
			const char *name = *(const char **)(0xB84CCC + 4 * p.a); // battle file name table
			std::vector<uint8_t> f = readfile(join(O.battle, name));
			if (!f.empty()) memcpy((void *)p.b, f.data(), f.size());
			if (p.c) ((void (__cdecl *)())p.c)();
		}
		for (const Pending &q : g_pending) v.push_back(q);
		g_pending.clear();
	}
}

static uint8_t *g_cast_act, *g_cast_tg;
static void build_battle()
{
	uint8_t *act = g_fake + 0x200, *tg = g_fake + 0x400, *mdl = g_fake + 0x1000;
	g_cast_act = act; g_cast_tg = tg;
	int nt = O.targets < 1 ? 1 : (O.targets > 3 ? 3 : O.targets);
	uint16_t mask = 0;
	// one action (BattleActionTaskData, 20 bytes): +0 attacker, +1 command (2 = magic), +6 effect,
	// +8 target data (24-byte records, +0 slot), +0x10 target count; targets = enemy slots 4, 5, 6
	act[0] = (uint8_t)O.caster;
	act[1] = 2;
	*(uint16_t *)(act + 6) = (uint16_t)O.eff;
	*(uint8_t **)(act + 8) = tg;
	act[0x10] = (uint8_t)nt;
	for (int k = 0; k < nt; k++)
	{
		int slot = 4 + k % 3;
		tg[0x18 * k] = (uint8_t)slot;
		mask |= (uint16_t)(1 << slot);
	}
	act[0x11] = 0;
	uint8_t *cast = (uint8_t *)0x1D99A78;     // g_MagicCastContext
	memset(cast, 0, 12);
	cast[0] = (uint8_t)O.caster;
	*(uint16_t *)(cast + 2) = mask;
	*(uint8_t **)(cast + 4) = act;
	*(uint32_t *)0x1D99A50 = (uint32_t)act;  // current action
	static uint8_t name[0x400] = { 0x31, 0x24, 0x31, 0x2E, 0x46, 0x3C, 0 }; // a monster name (Scan reads it)
	static uint8_t *name_ptr = name;
	for (int slot = 3; slot < 7; slot++) *(uint8_t ***)(0x1D27B10 + 0xD0 * slot) = &name_ptr;
	static uint8_t e74[7][0x100];            // per-entity state block (Pandemona reads it)
	for (int k = 0; k < 7; k++) *(uint8_t **)(0x1D972C0 + 0x9C * k + 0x74) = e74[k];
	// entities 0x1D972C0 + 0x9C * slot: party 0..2, enemies 4..6
	static const int16_t POS[7][3] = { { -1500, 0, 3000 }, { 0, 0, 3200 }, { 1500, 0, 3000 }, { 0, 0, 0 }, { 0, 0, -3000 }, { -1800, 0, -3200 }, { 1800, 0, -3200 } };
	for (int k = 0; k < 7; k++)
	{
		uint8_t *e = (uint8_t *)(0x1D972C0 + 0x9C * k);
		uint8_t *m = mdl + 0x4000 * k;
		e[0] = (k == 3) ? 0 : 2;
		*(int16_t *)(e + 0x1C) = POS[k][0]; *(int16_t *)(e + 0x1E) = POS[k][1]; *(int16_t *)(e + 0x20) = POS[k][2];
		*(int16_t *)(e + 0x24) = (int16_t)(-1200 - 100 * k);
		*(int16_t *)(e + 0x26) = (int16_t)(900 + 150 * k);
		*(int16_t *)(e + 0x40) = 0x1000; *(int16_t *)(e + 0x48) = 0x1000; *(int16_t *)(e + 0x50) = 0x1000;
		*(int32_t *)(e + 0x54) = POS[k][0]; *(int32_t *)(e + 0x58) = POS[k][1]; *(int32_t *)(e + 0x5C) = POS[k][2];
		*(uint8_t **)(e + 0x64) = m;
		*(uint8_t **)m = m + 0x100;
		m[0x100] = 32;
		*(int16_t *)(m + 0x100 + 2) = 0x100;
		m[0x104] = 3; m[0x105] = 0x85;
		for (int b = 0; b < 32; b++)
		{
			uint8_t *bm = m + 0x100 + 0x10 + 0x30 * b;
			*(int16_t *)(bm + 2) = 200;
			*(int16_t *)(bm + 0x10) = 0x1000; *(int16_t *)(bm + 0x18) = 0x1000; *(int16_t *)(bm + 0x20) = 0x1000;
			*(int32_t *)(bm + 0x28) = -100 * b;
		}
	}
	// battle camera (0x1D97778) and the GTE screen (OFX 160, OFY 112, H 0x280): a default view from
	// the party side looking at the enemies
	int16_t *cam = (int16_t *)0x1D97778;
	memset(cam, 0, 32);
	cam[0] = 0x1000; cam[4] = 0xF00; cam[5] = -0x5A8; cam[7] = 0x5A8; cam[8] = 0xF00;
	*(int32_t *)(cam + 10) = 0; *(int32_t *)(cam + 12) = 800; *(int32_t *)(cam + 14) = 7000;
	// 0x1D97708 is SOME_COORDINATE (the scratch point after the entity slots) and 0x1D97710.. the
	// camera shake offsets BS_Camera_BuildViewMatrixApplyShake adds to the view: both stay 0 (the
	// FFNx harness copied the camera matrix there, which put a 3840-unit shake into every view)
	memset((void *)0x1D97708, 0, 16);
	auto wc = [](int32_t v, int r) { ((void (__cdecl *)(int32_t, int))0x45D7F0)(v, r); };
	wc(160 << 16, 24); wc(112 << 16, 25); wc(0x280, 26);
	*(int16_t *)0x1CA92F0 = 0x155; *(int16_t *)0x1CA92F4 = 0x100; // GTE ZSF3 / ZSF4 as the game's GTE init
}

static bool run_queue(uint32_t q, int *r)
{
	__try { *r = ((int (__cdecl *)(uint32_t))0x508420)(q); return true; }
	__except (filter(GetExceptionInformation())) { return false; }
}
static bool call0(uint32_t fn) { __try { ((void (__cdecl *)())fn)(); return true; } __except (filter(GetExceptionInformation())) { return false; } }
// model=N: every slot but 3 gets c0mN.dat through the game's loader (BattleTask_DispatchComEntityLoad
// 0x507080 queues battle_monster_dat_loader in queue 0x1D98B40), posed on animation 0 frame 0
static bool pose_model(uint32_t e)
{
	__try
	{
		((int (__cdecl *)(uint32_t, uint32_t, uint32_t))0x509440)(e + 0x60, e + 0x6C, 0);
		((int (__cdecl *)(uint32_t))0x508C90)(e + 0x60);
		return true;
	}
	__except (filter(GetExceptionInformation())) { return false; }
}
static bool load_models()
{
	g_modelmem = (uint8_t *)VirtualAlloc(nullptr, MODELMEM_SIZE + MODELWORK_SIZE, MEM_COMMIT, PAGE_READWRITE);
	((void (__cdecl *)(uint32_t))0x507050)((uint32_t)g_modelmem);
	*(uint32_t *)0x1D98B3C = (uint32_t)g_modelmem + MODELMEM_SIZE;
	*(uint32_t *)0xB6D080 = (uint32_t)g_modelmem + MODELMEM_SIZE;
	static uint32_t out[7][2];
	for (int slot = 0; slot < 7; slot++)
	{
		if (slot == 3) continue;
		((void (__cdecl *)(uint32_t, uint32_t, uint32_t *))0x507080)(0x10 + O.model, (uint32_t)slot, out[slot]);
		bool done = false;
		for (int it = 0; it < 16 && !done; it++)
		{
			apply_pending(g_pending);
			int r = 0;
			if (!run_queue(0x1D98B40, &r)) { printf("model load (slot %d) faulted %08lX at eip %08lX\n", slot, g_fault_code, g_fault_eip); return false; }
			done = r == 0;
		}
		if (!done) { printf("model load (slot %d) did not finish\n", slot); return false; }
		uint32_t e = 0x1D972C0 + 0x9C * slot;
		*(uint32_t *)(e + 0x7C) = 0xFFFFFFFF;       // every object visible
		env_reset();
		pose_model(e);
		*(uint32_t *)(e + 0x28) = 0x808080;          // neutral model tint
	}
	g_pending.clear();
	return true;
}

// ---------------------------------------------------------------- camera file
struct CamPose { int16_t eye[3], at[3], roll; int32_t h; };
static std::map<int, CamPose> g_cams;
static void load_camera()
{
	FILE *f = fopen(O.camera.c_str(), "r");
	if (!f) { printf("cannot read the camera file %s\n", O.camera.c_str()); return; }
	int t, ex, ey, ez, ax, ay, az, roll, h;
	while (fscanf(f, "%d %d %d %d %d %d %d %d %d", &t, &ex, &ey, &ez, &ax, &ay, &az, &roll, &h) == 9)
		g_cams[t] = { { (int16_t)ex, (int16_t)ey, (int16_t)ez }, { (int16_t)ax, (int16_t)ay, (int16_t)az }, (int16_t)roll, h };
	fclose(f);
}
// the view of tick t: the camera words the battle camera player would hold, then the view matrix
// (BS_Camera_BuildViewMatrixApplyShake 0x5033E0) and the GTE projection distance H
static void set_camera(int t)
{
	auto it = g_cams.find(t);
	if (it == g_cams.end()) { if (g_cams.empty()) return; it = g_cams.upper_bound(t); if (it != g_cams.begin()) --it; }
	const CamPose &c = it->second;
	memcpy((void *)0xB8B7F0, c.eye, 6);
	memcpy((void *)0xB8B7F8, c.at, 6);
	*(int16_t *)0x1D977A2 = c.roll;
	if (!call0(0x5033E0)) printf("tick %d: view matrix build faulted %08lX at eip %08lX\n", t, g_fault_code, g_fault_eip);
	if (getenv("FXR_VIEW") && t < 2)
	{
		const int16_t *m = (const int16_t *)0x1D97778; const int32_t *tr = (const int32_t *)(0x1D97778 + 20);
		printf("tick %d view: %d %d %d / %d %d %d / %d %d %d  trans %d %d %d\n", t, m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], tr[0], tr[1], tr[2]);
	}
	((void (__cdecl *)(int32_t, int))0x45D7F0)(c.h > 0 ? c.h : 0x280, 26);
}

// ---------------------------------------------------------------- run
static bool run_setup()
{
	__try
	{
		uint32_t fn = 0;
		((void (__cdecl *)(int, uint32_t *))0x50AF20)(O.eff, &fn); // Magic_GetIDLoad
		*(uint16_t *)0x1D97728 = 0xFFFF;
		*(uint32_t *)C3_28 = ((uint32_t (__cdecl *)(uint32_t))fn)(0x1D99A78);
		return true;
	}
	__except (filter(GetExceptionInformation())) { return false; }
}
static __declspec(noinline) void clear_stack() { volatile uint8_t buf[0x30000]; memset((void *)buf, 0, sizeof(buf)); }
static bool run_tick(int *ret)
{
	clear_stack();
	__try
	{
		uint32_t q = *(uint32_t *)C3_28;
		*ret = q ? ((int (__cdecl *)(uint32_t))0x508420)(q) : 0;
		return true;
	}
	__except (filter(GetExceptionInformation())) { return false; }
}

static bool parse(int argc, char **argv)
{
	if (argc < 2) return false;
	O.eff = atoi(argv[1]);
	for (int i = 2; i < argc; i++)
	{
		std::string a = argv[i];
		if (a == "child") continue;
		size_t eq = a.find('=');
		if (eq == std::string::npos) continue;
		std::string k = a.substr(0, eq), v = a.substr(eq + 1);
		if (k == "exe") O.exe = v;
		else if (k == "magic") O.magic = v;
		else if (k == "battle") O.battle = v;
		else if (k == "out") O.out = v;
		else if (k == "camera") O.camera = v;
		else if (k == "model") O.model = atoi(v.c_str());
		else if (k == "ticks") O.ticks = atoi(v.c_str());
		else if (k == "targets") O.targets = atoi(v.c_str());
		else if (k == "caster") O.caster = atoi(v.c_str());
		else if (k == "seed") O.seed = (uint32_t)strtoul(v.c_str(), nullptr, 10);
	}
	return O.eff > 0 && O.eff < 400 && !O.exe.empty() && !O.out.empty();
}

int main(int argc, char **argv)
{
	setvbuf(stdout, nullptr, _IONBF, 0);
	if (!parse(argc, argv))
	{
		printf("usage: fxrecorder <effect id> exe=FF8_EN.exe magic=<dir> battle=<dir> out=<file> [model=N] [ticks=N] [targets=N] [caster=N] [seed=N] [camera=<file>]\n");
		return 1;
	}
	if (strcmp(argv[argc - 1], "child") != 0)
	{
		// the exe's image must sit at 0x400000: run again as a child whose 0x400000 is reserved first
		std::string cmd = std::string("\"") + argv[0] + "\"";
		for (int i = 1; i < argc; i++) cmd += std::string(" \"") + argv[i] + "\"";
		cmd += " child";
		STARTUPINFOA si = { sizeof(si) };
		PROCESS_INFORMATION pi;
		if (!CreateProcessA(nullptr, (char *)cmd.c_str(), nullptr, nullptr, TRUE, CREATE_SUSPENDED, nullptr, nullptr, &si, &pi)) { printf("CreateProcess failed\n"); return 1; }
		if (!VirtualAllocEx(pi.hProcess, (void *)0x400000, 0x242B000, MEM_RESERVE, PAGE_EXECUTE_READWRITE)) printf("child reserve failed (%lu)\n", GetLastError());
		ResumeThread(pi.hThread);
		WaitForSingleObject(pi.hProcess, INFINITE);
		DWORD code = 0;
		GetExitCodeProcess(pi.hProcess, &code);
		return (int)code;
	}

	uint8_t *img = (uint8_t *)VirtualAlloc((void *)0x400000, 0x242B000, MEM_COMMIT, PAGE_EXECUTE_READWRITE);
	if (img != (uint8_t *)0x400000) { printf("cannot map the exe image at 0x400000 (%lu)\n", GetLastError()); return 1; }
	std::vector<uint8_t> exe = readfile(O.exe);
	if (exe.size() < 0x1000) { printf("cannot read %s\n", O.exe.c_str()); return 1; }
	uint32_t pe = *(uint32_t *)(exe.data() + 0x3C);
	uint16_t ns = *(uint16_t *)(exe.data() + pe + 6), opt = *(uint16_t *)(exe.data() + pe + 20);
	if (*(uint32_t *)(exe.data() + pe + 52) != 0x400000) { printf("%s is not based at 0x400000: not the 2013 Steam FF8_EN.exe\n", O.exe.c_str()); return 1; }
	memcpy(img, exe.data(), 0x1000);
	for (int i = 0; i < ns; i++)
	{
		const uint8_t *s = exe.data() + pe + 24 + opt + 40 * i;
		uint32_t vs = *(uint32_t *)(s + 8), va = *(uint32_t *)(s + 12), rs = *(uint32_t *)(s + 16), ra = *(uint32_t *)(s + 20);
		if (va + vs > 0x242B000 || ra + (rs < vs ? rs : vs) > exe.size()) continue;
		memcpy(img + va, exe.data() + ra, rs < vs ? rs : vs);
	}
	g_out = fopen(O.out.c_str(), "w");
	if (!g_out) { printf("cannot write %s\n", O.out.c_str()); return 1; }

	// stubs: engine calls with side effects outside the effect
	patch_jmp(0x560578, (void *)my_getptd);
	patch_jmp(0x55CBD2, (void *)my_rand);
	patch_jmp(0x571900, (void *)s_loadtex);
	patch_jmp(0x40A0F0, (void *)s_40A0F0);
	patch_jmp(0x45C740, (void *)s_45C740); patch_jmp(0x45C7A0, (void *)s_45C7A0);
	patch_jmp(0x45C870, (void *)s_45C870); patch_jmp(0x45C8E0, (void *)s_45C8E0);
	uint32_t zero1[] = { 0x46B3A0, 0x46B3E0, 0x47E3C0, 0x4A2940, 0x4A2900, 0x4A8480, 0x501E40, 0x501F30, 0x504270, 0x506690, 0x5099A0, 0x403D99 };
	for (uint32_t a : zero1) patch_jmp(a, (void *)s_zero1);
	uint32_t zero2[] = { 0x46B450, 0x506BA0, 0x505C00, 0x505CE0, 0x46BD40, 0x512AA0, 0x512AC0 };
	for (uint32_t a : zero2) patch_jmp(a, (void *)s_zero2);
	uint32_t zero3[] = { 0x501330, 0x5013A0, 0x5018C0, 0x501460, 0x46BBC0, 0x47CF50 };
	for (uint32_t a : zero3) patch_jmp(a, (void *)s_zero3);
	patch_jmp(0x50A730, (void *)s_zero0);
	patch_jmp(0x46BB40, (void *)s_46BB40);
	patch_jmp(0x501860, (void *)s_501860);
	patch_jmp(0x48D0A0, (void *)s_48D0A0);
	patch_jmp(0x508480, (void *)s_508480);
	patch_jmp(0x4A29A0, (void *)s_4A29A0);
	patch_jmp(0x508630, (void *)s_508630);
	patch_jmp(0x5088A0, (void *)s_5088A0);
	patch_jmp(0x505DF0, (void *)s_505DF0);
	patch_jmp(0x505EB0, (void *)s_505EB0);
	patch_jmp(0x49ED30, (void *)s_49ED30); patch_jmp(0x4A2D60, (void *)s_4A2D60); patch_jmp(0x49F0A0, (void *)s_49F0A0);
	patch_jmp(0x5099D0, (void *)s_5099D0); patch_jmp(0x508C90, (void *)s_508C90); patch_jmp(0x5095B0, (void *)s_5095B0);
	patch_jmp(0x508F90, (void *)s_508F90); patch_jmp(0x509440, (void *)s_509440);
	*(uint32_t *)(g_ptd + 0x14) = O.seed;

	g_ot = (uint8_t *)VirtualAlloc(nullptr, OT_SIZE, MEM_COMMIT, PAGE_READWRITE);
	g_pkt = (uint8_t *)VirtualAlloc(nullptr, PKT_SIZE, MEM_COMMIT, PAGE_READWRITE);
	g_scr = (uint8_t *)VirtualAlloc(nullptr, SCR_SIZE, MEM_COMMIT, PAGE_READWRITE);
	g_fake = (uint8_t *)VirtualAlloc(nullptr, FAKE_SIZE, MEM_COMMIT, PAGE_READWRITE);
	*(uint32_t *)0x1D98420 = 0;
	build_battle();
	if (!O.camera.empty()) load_camera();
	// the battle's shared effect textures (load_aA8defTim 0x508660: battle file 163, a8def.tim)
	std::vector<uint8_t> a8def = readfile(join(O.battle, "a8def.tim"));
	if (!a8def.empty()) dump_tim(0, a8def.data());
	else printf("no a8def.tim in %s: the battle's shared effect textures are missing\n", O.battle.c_str());
	if (O.model >= 0 && !load_models()) return 1;
	call0(0x56F9A0); // BS_memsetVars2: hit-effect queue (screen fades...)
	env_reset();
	if (!run_setup()) { printf("setup faulted %08lX at eip %08lX addr %08lX\n", g_fault_code, g_fault_eip, g_fault_addr); return 1; }
	printf("effect %d: setup ok\n", O.eff);
	std::vector<Pending> keep = g_pending;
	int t = 0;
	for (; t < O.ticks; t++)
	{
		g_tick = t;
		g_cur_tick_pad = t;
		apply_pending(keep);
		dump_vram_queue();                 // uploads queued by the setup / the loads applied before this tick
		env_reset();
		set_camera(t);
		g_ins.clear(); g_pending.clear();
		g_rec = true;
		int r = 0;
		bool ok = run_tick(&r);
		g_rec = false;
		if (!ok) { printf("tick %d faulted %08lX at eip %08lX addr %08lX\n", t, g_fault_code, g_fault_eip, g_fault_addr); break; }
		dump_vram_queue();                 // uploads this tick queued
		write_tick(t);
		keep = g_pending;
		if (r == 0 || *(uint32_t *)C3_28 == 0) { t++; break; }
	}
	fclose(g_out);
	printf("done: effect %d, %d ticks recorded\n", O.eff, t);
	return 0;
}
