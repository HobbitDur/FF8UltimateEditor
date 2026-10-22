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
// [modelfile=<file>: that .dat is read for the model instead of <battle>/c0mN.dat] [actors=0: the
// models are loaded but not drawn; by default each tick draws them as the battle does]
// [slotK=<file> (K = 0-2 party, 3-6 enemies, as the battle's entities): the battle's cast instead of model=, one body per
// slot - a monster c0mNNN.dat or a character d?cNNN.dat (its d?wNNN.dat with weaponK=<file>);
// slots without a file stay empty] [target=K[,K..]: the effect's targets, any slot] [posK=x,y,z /
// yawK=N (4096ths of a turn): where slot K stands and faces, default fixed places, party facing
// the enemies]
// [overrides=<folder>: unsaved effect-file snapshots, preferred over magic= without changing it]
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
#include <algorithm>

// ---------------------------------------------------------------- options
struct Opt
{
	int eff = 0, ticks = 3000, targets = 1, caster = 0, model = 0;
	uint32_t seed = 12345;
	std::string exe, magic, battle, out, camera, overrides;
	std::string body[7], weapon[7];   // slotK= / weaponK=: the battle's cast, one file per slot
	std::vector<int> target_slots;    // target=K[,K..]: the effect's targets (default: enemy slots 3..)
	bool placed[7] = {}; int pos[7][3] = {}; int yaw[7] = { 0, 0, 0, 2048, 2048, 2048, 2048 }; // posK= / yawK=
	bool cast() const { for (int k = 0; k < 7; k++) if (!body[k].empty()) return true; return false; }
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
	std::vector<uint8_t> v;
	if (!O.overrides.empty()) v = readfile(join(O.overrides, name));
	if (v.empty()) v = readfile(join(O.magic, name));
	if (v.empty()) { printf("missing effect file %s\n", name); return 0; }
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
static int g_guard_faults = 0;
#define GUARDED(ADDR, CALL, FALLBACK) \
	unpatch(ADDR); uint32_t r; \
	__try { r = (uint32_t)(CALL); } __except (filter(GetExceptionInformation())) { r = (uint32_t)(FALLBACK); \
		if (getenv("FXR_GUARD") && g_guard_faults++ < 12) printf("guarded %06X faulted %08lX at eip %08lX addr %08lX\n", ADDR, g_fault_code, g_fault_eip, g_fault_addr); } \
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
static void write_packet(uint32_t fn, uint32_t bucket, uint32_t pkt)
{
	if (IsBadReadPtr((void *)pkt, 4)) return;
	uint32_t len = *(const uint8_t *)(pkt + 3);
	if (IsBadReadPtr((void *)(pkt + 4), len * 4)) return;
	fprintf(g_out, "P 0 0 0 0 0 0 0 %X %X %u", fn, bucket, len);
	for (uint32_t k = 0; k < len; k++) fprintf(g_out, " %X", *(const uint32_t *)(pkt + 4 + 4 * k));
	fprintf(g_out, "\n");
}
static void walk_render_list(std::vector<Ins> &out); // the PC draw order (below, after the battle memory)
static void write_tick(int t)
{
	if (!g_out) return;
	// Everything the tick drew, in the order the PC draws it (the render list walk), then any hooked
	// insertion the walk did not reach (a list outside the frame's ordering table)
	std::vector<Ins> drawn;
	walk_render_list(drawn);
	std::map<uint32_t, bool> seen;
	for (const Ins &r : drawn) seen[r.pkt] = true;
	for (const Ins &r : g_ins) if (!seen.count(r.pkt)) { drawn.push_back(r); seen[r.pkt] = true; }
	fprintf(g_out, "R %d %u ordered\n", t, (unsigned)drawn.size());
	for (const Ins &r : drawn) write_packet(r.fn, r.bucket, r.pkt);
	const int16_t *eye = (const int16_t *)0xB8B7F0, *at = (const int16_t *)0xB8B7F8;
	fprintf(g_out, "C %d %d %d %d %d %d %d\n", t, eye[0], eye[1], eye[2], at[0], at[1], at[2]);
}

// ---------------------------------------------------------------- battle memory
static uint8_t *g_ot, *g_pkt, *g_scr, *g_fake, *g_modelmem;
static const uint32_t OT_SIZE = 0x20000, PKT_SIZE = 0x400000, SCR_SIZE = 0x40000, FAKE_SIZE = 0x40000;
static const uint32_t MODELMEM_SIZE = 0x400000, MODELWORK_SIZE = 0x40000;
static const uint32_t C3_28 = 0x1D96AAC; // running effect root queue

// Everything the frame draws, as SSIGPU keeps it: every insert (SSIGPU_InsertPrim* 0x45C740.., and
// the model renderer's own inline inserts, which the hooks above never see) appends an
// SSIGPU_ExecNode {pkt, 4 depth keys = the GTE SZ of its points, msk, prev head byte} at the cursor
// 0x1CA8828. Listed far to near by their deepest key (what the PlayStation's depth buckets do), in
// insertion order among equals; prims with no depth keys (2D) last, on top.
static const uint32_t EXEC_START = 0x1C48828, EXEC_CURSOR = 0x1CA8828;
static void walk_render_list(std::vector<Ins> &out)
{
	uint32_t start = EXEC_START, end = *(const uint32_t *)EXEC_CURSOR;
	if (end <= start || end - start > 0x60000) return;
	struct Node { int32_t depth; uint32_t order, pkt; };
	std::vector<Node> nodes;
	for (uint32_t node = start; node + 24 <= end; node += 24)
	{
		uint32_t pkt = *(const uint32_t *)node;
		if (IsBadReadPtr((void *)pkt, 8)) continue;
		const int32_t *k = (const int32_t *)(node + 4);
		int32_t depth = k[0];
		for (int i = 1; i < 4; i++) if (k[i] > depth) depth = k[i];
		nodes.push_back({ depth > 0 ? depth : -1, (uint32_t)nodes.size(), pkt });
	}
	std::stable_sort(nodes.begin(), nodes.end(), [](const Node &a, const Node &b) { return a.depth > b.depth; });
	for (const Node &n : nodes) out.push_back({ 0, (uint32_t)n.depth, n.pkt });
}

static void env_reset()
{
	*(uint32_t *)0x1CA8828 = 0x1C48828;       // SSIGPU prim pool cursor
	memset(g_ot, 0, OT_SIZE);
	*(uint32_t *)0x1D8E04C = (uint32_t)g_ot;   // g_Battle_FrameRenderListBase
	*(uint32_t *)0x1D8E054 = (uint32_t)g_pkt;  // frame packet cursor
	*(uint32_t *)0x1D969A8 = (uint32_t)g_pkt + PKT_SIZE;
	*(uint32_t *)0x1D999C4 = (uint32_t)g_scr;  // Field_Alloc stack
}

static std::string g_modelfile;   // modelfile=: the target model's .dat, read instead of <battle>/c0mNNN.dat
static std::string g_serve;       // the file a load in progress reads instead of the battle file it names
static int g_actors = 1;          // actors=0: do not draw the battle's models
static bool g_drawn_slot[7];      // the slots holding a model
// a party slot's weapon (BattleAnimHeader + its anim cmd + attach rotation/offset: 68 bytes at
// TASK_QUEUE_BATTLE_ENTITY.data + 17 dwords per slot), 0 for monsters, Zell, Edea and Kiros
static uint32_t weapon_header(uint32_t e) { return *(uint32_t *)(e + 0x78); }
// the battle's models, as each entity's task draws them every tick (pre_pre_linkedToAnimationSequence
// 0x502AB0: BattleEntity_ComputeViewBounds 0x5086F0 + BS_RenderBattleEntity 0x502D40) unless the entity
// is hidden - an effect that redraws its target (Cure's overlay) hides it for that time. Each
// actor plays animation 0 (the wait pose) in a loop, body and weapon in lockstep, one frame per
// tick as the battle does: the tick's frame is drawn, then the animation advances
// (AdvanceAnimationBy1AndCheckCompletion 0x5094F0; at its end Battle_QueueAnimation 0x509520
// starts it again). The draw composes the bone matrices in place, so they are rebuilt from the
// pose first (BattleModel_RebuildBodyAndWeaponMatrices 0x508F60), with the weapon's attach
// transform (pre_pre_linkedToAnimationSequence 0x502CEA)
static bool render_actor(uint32_t e)
{
	__try
	{
		((int (__cdecl *)(uint32_t))0x508F60)(e);
		if (uint32_t w = weapon_header(e))
		{
			((void (__cdecl *)(uint32_t, uint32_t))0x56CE30)(w + 20, w + 36);   // ComposeZYXRotationMatrix
			*(int32_t *)(w + 56) = *(int16_t *)(w + 28);
			*(int32_t *)(w + 60) = *(int16_t *)(w + 30);
			*(int32_t *)(w + 64) = *(int16_t *)(w + 32);
		}
		((int (__cdecl *)(uint32_t))0x5086F0)(e);
		((int (__cdecl *)(uint32_t))0x502D40)(e);
		if (((int (__cdecl *)(uint32_t))0x5094F0)(e) == 1)                    // READ_ANIMATION_RETURN_ANIMATION_COMPLETE
			((int (__cdecl *)(uint32_t, int))0x509520)(e, 0);
		return true;
	}
	__except (filter(GetExceptionInformation())) { return false; }
}
static void render_actors()
{
	if (!g_actors) return;
	for (int k = 0; k < 7; k++)
	{
		if (!g_drawn_slot[k]) continue;
		uint32_t e = 0x1D972C0 + 0x9C * k;
		uint8_t flags = *(uint8_t *)e;
		uint16_t combat = *(uint16_t *)(e + 2);
		bool drawn = (flags & 0x02) && !(flags & 0x04) && !(combat & (0x04 | 0x80));
		uint32_t cur0 = *(uint32_t *)0x1CA8828, pk0 = *(uint32_t *)0x1D8E054;
		bool ok = drawn ? render_actor(e) : true;
		if (getenv("FXR_ACTORS") && g_tick < 3)
			printf("tick %d slot %d flags %02X combat %04X drawn %d ok %d nodes +%u packets +%u\n", g_tick, k, flags, combat, drawn, ok,
				(*(uint32_t *)0x1CA8828 - cur0) / 24, *(uint32_t *)0x1D8E054 - pk0);
	}
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
			std::vector<uint8_t> f;
			if (!g_serve.empty()) f = readfile(g_serve);                     // the slot's chosen file
			else if (!g_modelfile.empty() && _strnicmp(name, "c0m", 3) == 0) f = readfile(g_modelfile); // the chosen .dat
			if (f.empty() && g_serve.empty()) f = readfile(join(O.battle, name));
			if (!f.empty()) memcpy((void *)p.b, f.data(), f.size());
			else printf("missing battle file %s\n", g_serve.empty() ? name : g_serve.c_str());
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
	// +8 target data (24-byte records, +0 slot), +0x10 target count; targets = enemy slots 3, 4, 5 unless target= names them
	act[0] = (uint8_t)O.caster;
	act[1] = 2;
	*(uint16_t *)(act + 6) = (uint16_t)O.eff;
	*(uint8_t **)(act + 8) = tg;
	act[0x10] = (uint8_t)nt;
	if (!O.target_slots.empty()) nt = (int)O.target_slots.size() > 3 ? 3 : (int)O.target_slots.size();
	for (int k = 0; k < nt; k++)
	{
		int slot = O.target_slots.empty() ? 3 + k % 4 : O.target_slots[k];
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
	// entities 0x1D972C0 + 0x9C * slot: party 0..2, enemies 3..6 (the game's layout)
	static const int16_t POS[7][3] = { { -1500, 0, 3000 }, { 0, 0, 3200 }, { 1500, 0, 3000 }, { 0, 0, -3000 }, { -1800, 0, -3200 }, { 1800, 0, -3200 }, { 0, 0, -4600 } };
	for (int k = 0; k < 7; k++)
	{
		uint8_t *e = (uint8_t *)(0x1D972C0 + 0x9C * k);
		uint8_t *m = mdl + 0x4000 * k;
		e[0] = 2;
		const int *at = O.placed[k] ? O.pos[k] : nullptr;
		int16_t x = at ? (int16_t)at[0] : POS[k][0], y = at ? (int16_t)at[1] : POS[k][1], z = at ? (int16_t)at[2] : POS[k][2];
		*(int16_t *)(e + 0x1C) = x; *(int16_t *)(e + 0x1E) = y; *(int16_t *)(e + 0x20) = z;
		*(int16_t *)(e + 0x24) = (int16_t)(-1200 - 100 * k);
		*(int16_t *)(e + 0x26) = (int16_t)(900 + 150 * k);
		*(int16_t *)(e + 0x40) = 0x1000; *(int16_t *)(e + 0x48) = 0x1000; *(int16_t *)(e + 0x50) = 0x1000;
		*(int32_t *)(e + 0x54) = x; *(int32_t *)(e + 0x58) = y; *(int32_t *)(e + 0x5C) = z;
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
// model=N: every slot gets c0mN.dat through the game's loader (BattleTask_DispatchComEntityLoad
// 0x507080 queues battle_monster_dat_loader in queue 0x1D98B40), posed on animation 0 frame 0
static bool pose_model(uint32_t e)
{
	__try
	{
		((int (__cdecl *)(uint32_t, int))0x509520)(e, 0);   // Battle_QueueAnimation: body and weapon, frame 0
		return true;
	}
	__except (filter(GetExceptionInformation())) { return false; }
}
// one queued load (BattleTask_DispatchComEntityLoad 0x507080) run to its end, file requests
// answered with serve (or the battle file named)
static bool load_entity(int com_id, int slot, const std::string &serve)
{
	static uint32_t out[7][2];
	g_serve = serve;
	((void (__cdecl *)(uint32_t, uint32_t, uint32_t *))0x507080)((uint32_t)com_id, (uint32_t)slot, out[slot]);
	bool done = false;
	for (int it = 0; it < 16 && !done; it++)
	{
		apply_pending(g_pending);
		int r = 0;
		if (!run_queue(0x1D98B40, &r)) { printf("model load (slot %d) faulted %08lX at eip %08lX\n", slot, g_fault_code, g_fault_eip); g_serve.clear(); return false; }
		done = r == 0;
	}
	g_serve.clear();
	if (!done) printf("model load (slot %d) did not finish\n", slot);
	// its texture uploads now: they point into the file buffer the next load overwrites
	dump_vram_queue();
	return done;
}
// the com id of a body file: c0mNNN.dat = monster 0x10 + NNN, d<X>c###.dat = character X (Squall 0
// .. Ward 10: PartyModelsArray 0xB8B914's order), -1 otherwise
static int body_com_id(const std::string &path)
{
	size_t cut = path.find_last_of("/\\");
	std::string name = path.substr(cut == std::string::npos ? 0 : cut + 1);
	if (name.size() >= 6 && _strnicmp(name.c_str(), "c0m", 3) == 0) return 0x10 + atoi(name.c_str() + 3);
	if (name.size() >= 3 && tolower(name[0]) == 'd' && tolower(name[2]) == 'c' && isxdigit((unsigned char)name[1]))
		return (int)strtol(name.substr(1, 1).c_str(), nullptr, 16);
	return -1;
}
// a party slot as initWeaponAnim 0x502670 + initAnimationSequenceAtStartBattle 0x5027D0 set it: com
// id, weapon slot, then the body (Battle_isLoadSquallEtc) and its weapon file (Battle_LoadWeaponry,
// com id + 0x1000), bound with their animations (setComFileData 0x502270, mask 4)
static bool load_character(uint32_t e, int slot, int com, const std::string &body, const std::string &weapon)
{
	*(uint8_t *)(e + 4) = (uint8_t)com;
	*(uint8_t *)(e + 0x80) = 0;                                      // weaponTier
	*(uint8_t *)(e + 0x81) = 0;                                      // linkedAltModel
	// Zell, Edea, Kiros: no weapon model; nor a character whose weapon file is not given
	bool armed = com != 1 && com != 7 && com != 9 && !weapon.empty();
	uint32_t w = armed ? 0x1D971F0 + 68 * slot : 0;
	*(uint32_t *)(e + 0x78) = w;
	if (w) memset((void *)w, 0, 68);
	*(uint32_t *)(e + 0x74) = 0x1D96ED0 + 64 * slot;                // BattleStateEntity[slot]
	if (!load_entity(com, slot, body)) return false;
	if (com != 7 && !weapon.empty() && !load_entity(0x1000 + com, slot, weapon)) return false;
	uint32_t extra = *(uint32_t *)0x1D999BC + 12320 * slot;          // g_PartyExtraAnimSlots[slot]
	auto bind = (void (__cdecl *)(uint32_t, uint32_t, int))0x502270;
	if (*(uint32_t *)(extra + 8))
	{
		bind(e + 0x60, extra, 4);
		if (w) bind(w, extra + 16, 4);
	}
	*(uint32_t *)(e + 0x68) = *(uint32_t *)(e + 0x64);              // comFileDataBis
	if (w) *(uint32_t *)(w + 8) = *(uint32_t *)(w + 4);
	return true;
}
static bool load_models()
{
	g_modelmem = (uint8_t *)VirtualAlloc(nullptr, MODELMEM_SIZE + MODELWORK_SIZE, MEM_COMMIT, PAGE_READWRITE);
	call0(0x508260);   // BS_SetLocation1: command queue table, texture slots 0-5 kept for the party
	((void (__cdecl *)(uint32_t))0x507050)((uint32_t)g_modelmem);
	*(uint32_t *)0x1D98B3C = (uint32_t)g_modelmem + MODELMEM_SIZE;
	*(uint32_t *)0xB6D080 = (uint32_t)g_modelmem + MODELMEM_SIZE;
	bool cast = O.cast();
	// the game keeps a character's model data under its com id (COMMAND_QUEUE_TABLE): a battle never
	// has one character twice, so a second Squall (d0c001 and d0c000) gets a free character id - its
	// files are given here, the id only keeps the two apart
	bool char_used[16] = {};
	for (int slot = 0; slot < 7; slot++)
	{
		uint32_t e = 0x1D972C0 + 0x9C * slot;
		if (cast)
		{
			if (O.body[slot].empty()) continue;
			int com = body_com_id(O.body[slot]);
			if (com < 0) { printf("slot %d: %s is neither c0mNNN.dat nor d?c###.dat\n", slot, O.body[slot].c_str()); continue; }
			if (com < 0x10 && char_used[com])
			{
				// the same kind: armed (weapon model) or not (Zell 1, Kiros 9); never Edea's own loader (7)
				static const int ARMED[] = { 0, 2, 3, 4, 5, 6, 8, 10 }, BARE[] = { 1, 9 };
				bool armed = com != 1 && com != 9 && com != 7;
				const int *free_ids = armed ? ARMED : BARE; int n = armed ? 8 : 2;
				for (int i = 0; i < n; i++) if (!char_used[free_ids[i]]) { com = free_ids[i]; break; }
			}
			if (com < 0x10) char_used[com] = true;
			if (com < 0x10 ? !load_character(e, slot, com, O.body[slot], O.weapon[slot]) : !load_entity(com, slot, O.body[slot])) return false;
		}
		else if (!load_entity(0x10 + O.model, slot, "")) return false;
		g_drawn_slot[slot] = true;
		*(uint32_t *)(e + 0x7C) = 0xFFFFFFFF;       // every object visible
		// the neutral battle facing (resetBasedRotation 0x502070): party 0, monsters turned to them
		*(int16_t *)(e + 12) = 0; *(int16_t *)(e + 14) = (int16_t)O.yaw[slot]; *(int16_t *)(e + 16) = 0;
		((void (__cdecl *)(uint32_t, uint32_t))0x56CE30)(e + 12, e + 0x40);
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
		else if (k == "overrides") O.overrides = v;
		else if (k == "battle") O.battle = v;
		else if (k == "out") O.out = v;
		else if (k == "camera") O.camera = v;
		else if (k == "modelfile") g_modelfile = v;
		else if (k == "actors") g_actors = atoi(v.c_str());
		else if (k == "model") O.model = atoi(v.c_str());
		else if (k == "ticks") O.ticks = atoi(v.c_str());
		else if (k == "targets") O.targets = atoi(v.c_str());
		else if (k == "caster") O.caster = atoi(v.c_str());
		else if (k == "seed") O.seed = (uint32_t)strtoul(v.c_str(), nullptr, 10);
		else if (k == "target")
		{
			for (size_t at = 0; at < v.size();)
			{
				size_t comma = v.find(',', at);
				O.target_slots.push_back(atoi(v.substr(at, comma - at).c_str()));
				at = comma == std::string::npos ? v.size() : comma + 1;
			}
		}
		else if (k.size() == 5 && k.compare(0, 4, "slot") == 0 && k[4] >= '0' && k[4] <= '6') O.body[k[4] - '0'] = v;
		else if (k.size() == 4 && k.compare(0, 3, "pos") == 0 && k[3] >= '0' && k[3] <= '6')
		{
			int s = k[3] - '0';
			O.placed[s] = sscanf(v.c_str(), "%d,%d,%d", &O.pos[s][0], &O.pos[s][1], &O.pos[s][2]) == 3;
		}
		else if (k.size() == 4 && k.compare(0, 3, "yaw") == 0 && k[3] >= '0' && k[3] <= '6') O.yaw[k[3] - '0'] = atoi(v.c_str()) & 4095;
		else if (k.size() == 7 && k.compare(0, 6, "weapon") == 0 && k[6] >= '0' && k[6] <= '6') O.weapon[k[6] - '0'] = v;
	}
	return O.eff > 0 && O.eff < 400 && !O.exe.empty() && !O.out.empty();
}

int main(int argc, char **argv)
{
	setvbuf(stdout, nullptr, _IONBF, 0);
	if (!parse(argc, argv))
	{
		printf("usage: fxrecorder <effect id> exe=FF8_EN.exe magic=<dir> battle=<dir> out=<file> [overrides=<dir>] [model=N] [modelfile=<file>] [slotK=<file>] [weaponK=<file>] [target=K,..] [actors=0|1] [ticks=N] [targets=N] [caster=N] [seed=N] [camera=<file>]\n");
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
	else printf("missing battle file a8def.tim (the battle's shared effect textures)\n");
	if ((O.cast() || O.model >= 0) && !load_models()) return 1;
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
		if (ok) render_actors();
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
