// Effect programs: an effect run from its description alone (docs/fujin-effect-description.md).
//
// Fujin compiles an effect's description (FF8GameData/Resources/json/effects/effect_NNN.json:
// its parameters, its tasks - phases, motion, spawns, events, draws - and where its copy lives)
// into a program (Fujin/effectprogram.py), a text file of one directive per line. This header
// loads such a program and runs the effect from it: every directive names a piece of FFNx's parts
// library (fx_parts.h, fx_overlay.h - their inputs, behaviours and renderers) with its arguments,
// literal numbers or parameters ($index). A task's tick runs, in this order: its every-tick
// actions, its current phase (each-tick actions, then its wait condition: when it holds, the
// phase's actions and the next phase), its motion (and the spawns of each of its steps), its
// spawns, its events, its draws, then its counter and its end (done, no live child).
//
// The director (the root task), the setup and the file loader are the effect library's
// per-action director: one emitter per action, in turn, until every queue is empty.
//
// A program can stand in for an effect of the exe (its `function` addresses: the recorder jumps
// from each original to the program's thunk) or be a new one (no address: the thunks are the
// task functions).

#pragma once

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <map>
#include <string>
#include <vector>

#include "mag_heal_ring_code.h"

namespace fxprog
{
	using namespace ff8fx;
	using namespace ff8fx::eng;
	using namespace ff8fx::magc;
	using namespace ff8fx::parts;
	using ff8fx::healring::EmitterNode;
	using ff8fx::healring::Particle;
	using ff8fx::healring::RootNode;
	using ff8fx::overlay::OverlayCtx;

	struct Val { bool param = false; int32_t v = 0; };
	struct Param { std::string key, type, text; int32_t value = 0, game = 0; };
	struct Step { int op = 0; std::vector<Val> a; };
	struct Phase { std::vector<Step> each_tick; Step wait; std::vector<Step> act; };
	struct Spawn { int task = -1; int gate = 0; Val first, last; Val schedule[8]; Step place; };
	struct Draw { int tag = 0; int gate = 0; bool limited = false; Val below; Step draw; };
	struct Task
	{
		std::string key;
		int pool = 0, size = 0;
		uint32_t function = 0;                    // the original it stands in for (0: a new task)
		std::vector<Step> every_tick;
		std::vector<Phase> phases;
		Step motion;
		std::vector<Spawn> step_spawns, spawns;
		std::vector<Step> events;
		std::vector<Draw> draws;
	};
	struct Pool { uint32_t queue = 0, storage = 0; int size = 0, count = 0, tag = -1; };
	struct Program
	{
		int effect = 0;
		std::string name;
		std::map<std::string, uint32_t> memory;
		uint32_t file_loader = 0, setup = 0, root = 0, camera = 0, texture_name = 0;
		int texture_param = -1, director_spawns = -1;
		std::vector<Pool> pools;
		std::vector<Param> params;
		std::vector<Task> tasks;
	};

	enum Op
	{
		NONE,
		// actions
		FOLLOW_TARGET, SPAWN, HEAL, DONE, SPAWNING, OVERLAY, SEQUENCE, FLIPBOOK, HELIX_START, OVERLAY_START,
		HIDE_TARGET, SHOW_TARGET, UNBLOCK_DIRECTOR, VELOCITY_ROLL, VELOCITY_RISE, DRIFT, SOUND_AT,
		// conditions
		TICK_AT_LEAST, FLIPBOOK_END,
		// motions
		HELIX,
		// placements
		CIRCLE_DROP, GLINT, AT_PARENT,
		// draws
		SPRITE, GROUND_FLIPBOOK, PROJECTOR_OVERLAY,
	};
	static const std::map<std::string, int> OPS = {
		{ "none", NONE }, { "follow_target", FOLLOW_TARGET }, { "spawn", SPAWN }, { "heal", HEAL }, { "done", DONE },
		{ "spawning", SPAWNING }, { "overlay", OVERLAY }, { "sequence", SEQUENCE }, { "flipbook", FLIPBOOK },
		{ "helix_start", HELIX_START }, { "overlay_start", OVERLAY_START }, { "hide_target", HIDE_TARGET },
		{ "show_target", SHOW_TARGET }, { "unblock_director", UNBLOCK_DIRECTOR }, { "velocity_roll", VELOCITY_ROLL },
		{ "velocity_rise", VELOCITY_RISE }, { "drift", DRIFT }, { "sound_at", SOUND_AT },
		{ "tick_at_least", TICK_AT_LEAST }, { "flipbook_end", FLIPBOOK_END }, { "helix", HELIX },
		{ "circle_drop", CIRCLE_DROP }, { "glint", GLINT }, { "at_parent", AT_PARENT },
		{ "sprite", SPRITE }, { "ground_flipbook", GROUND_FLIPBOOK }, { "projector_overlay", PROJECTOR_OVERLAY },
	};

	inline Program *g_program = nullptr;

	// ------------------------------------------------------------------
	// Values
	// ------------------------------------------------------------------
	inline int32_t V(const Val &x) { return x.param ? g_program->params[x.v].value : x.v; }
	inline int32_t G(const Val &x) { return x.param ? g_program->params[x.v].game : x.v; }     // the game's value
	inline uint32_t Mem(const char *name) { return g_program->memory[name]; }
	inline uint32_t &PacketCursor() { return var<uint32_t>(Mem("packet_cursor")); }
	inline OverlayCtx &Overlay() { return var<OverlayCtx>(Mem("overlay_ctx")); }

	// a value as its parameter's type stores it (i16 wraps to 16 bits, u8 to 8...)
	inline int32_t as_type(const std::string &type, int32_t v)
	{
		if (type == "i16") return (int16_t)v;
		if (type == "u8") return (uint8_t)v;
		return v;
	}

	inline uint32_t __cdecl RunTask(int k, TaskNode *n);
	template<int K> uint32_t __cdecl TaskThunk(TaskNode *n) { return RunTask(K, n); }
	inline TaskFn const THUNKS[] = {
		TaskThunk<0>, TaskThunk<1>, TaskThunk<2>, TaskThunk<3>, TaskThunk<4>, TaskThunk<5>, TaskThunk<6>, TaskThunk<7>,
		TaskThunk<8>, TaskThunk<9>, TaskThunk<10>, TaskThunk<11>, TaskThunk<12>, TaskThunk<13>, TaskThunk<14>, TaskThunk<15>,
	};
	inline uint32_t TaskFunction(int k)
	{
		const Task &t = g_program->tasks[k];
		return t.function ? t.function : (uint32_t)THUNKS[k];
	}
	inline FxNode *SpawnTask(int k, void *parent)
	{
		const Task &t = g_program->tasks[k];
		const Pool &pool = g_program->pools[t.pool];
		return AddEffectTask((TaskQueue *)pool.queue, TaskFunction(k), t.size, parent);
	}

	// ------------------------------------------------------------------
	// Actions and conditions
	// ------------------------------------------------------------------
	inline void Act(const Step &s, TaskNode *n)
	{
		FxNode *h = (FxNode *)n;
		Particle *p = (Particle *)n;
		const std::vector<Val> &a = s.a;
		switch (s.op)
		{
		case FOLLOW_TARGET:
			Emitter_UpdatePos(n);
			Emitter_ComputeModelBounds(n);
			break;
		case SPAWN: SpawnTask(V(a[0]), n); break;
		case HEAL: ApplyActionResultToTarget(h->ctx->actions[h->action].targets + h->target * TARGET_STRIDE); break;
		case DONE: *(uint8_t *)&h->flags |= 1; break;
		case SPAWNING:
			if (V(a[0])) *(uint8_t *)&h->flags |= 2;
			else *(uint8_t *)&h->flags &= 0xFD;
			break;
		case OVERLAY:
			if (V(a[0])) *(uint8_t *)&h->flags |= 8;
			else *(uint8_t *)&h->flags &= 0xF7;
			break;
		case SEQUENCE: p->seq = fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])); break;
		case FLIPBOOK:
			p->seq = fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0]));
			p->last = fxp::last_frame(p->seq, (int16_t)V(a[1]));
			break;
		case HELIX_START: // above, radius num / den / max, climb above / ticks, steps per tick
		{
			CopyAnchorXZFromSource(p, p->center);
			p->center[1] = (int16_t)((int16_t)BoundsMaxWorldY(p) - (int16_t)V(a[0]));     // y down
			const fxp::Scaled radius = { (int16_t)V(a[1]), (int16_t)V(a[2]), (int16_t)V(a[3]) };
			p->radius = radius.of(BoundsRadius(p));
			FX_NOTE("target radius", BoundsRadius(p));
			FX_NOTE("target height", (int16_t)BoundsHeight(p));
			FX_NOTE("ring radius", p->radius);
			const int32_t hv = (int32_t)(int16_t)BoundsHeight(p) + (int16_t)V(a[4]);
			const int32_t q = hv / -(int16_t)V(a[5]);
			p->vel[1] = (int16_t)((int32_t)(int16_t)q / (int16_t)V(a[6]));
			FX_NOTE("ring rise per step", -p->vel[1]);
			FX_NOTE("ring start above feet", (int16_t)V(a[0]));
			break;
		}
		case OVERLAY_START: // r, g, b, light distance
		{
			const uint8_t rgb[3] = { (uint8_t)V(a[0]), (uint8_t)V(a[1]), (uint8_t)V(a[2]) };
			overlay::SetupTargetOverlay(&Overlay(), Mem("overlay_a00"), (uint8_t *)Mem("overlay_sprite"), Mem("overlay_verts"),
			                            Entity(h->slot), h->slot, &PacketCursor(), rgb, V(a[3]));
			*(uint8_t *)&h->flags |= 8;
			break;
		}
		case HIDE_TARGET: Entity(h->slot)[0] |= 4; break;
		case SHOW_TARGET: *(uint16_t *)Entity(h->slot) &= 0xFFFB; break;
		case UNBLOCK_DIRECTOR: ((RootNode *)h->root)->busy = 0; break;
		case VELOCITY_ROLL: // x min / max, y min / max, z min / max
		{
			const fxp::Range3 speed = { { (int16_t)V(a[0]), (int16_t)V(a[1]) }, { (int16_t)V(a[2]), (int16_t)V(a[3]) },
			                            { (int16_t)V(a[4]), (int16_t)V(a[5]) } };
			RollVelocity(p->vel, speed);
			break;
		}
		case VELOCITY_RISE: // min, max
		{
			const fxp::Range rise = { (int16_t)V(a[0]), (int16_t)V(a[1]) };
			p->vel[1] = (int16_t)-rise.roll(CrtRand());
			p->vel[0] = 0;
			p->vel[2] = 0;
			break;
		}
		case DRIFT: Drift(p->h.pos, p->vel); break;
		case SOUND_AT: // tick, sound, pan
			if (h->counter == V(a[0])) BdPlaySE((const void *)fxp::sound((uint32_t)V(a[1]), (uint32_t)G(a[1])), 0, V(a[2]));
			break;
		default: break;
		}
	}

	inline bool Holds(const Step &s, TaskNode *n)
	{
		FxNode *h = (FxNode *)n;
		Particle *p = (Particle *)n;
		switch (s.op)
		{
		case TICK_AT_LEAST: return h->counter >= V(s.a[0]);
		case FLIPBOOK_END: return FlipbookExpired(p->frame, p->last, p->h.flags);
		default: return true;
		}
	}

	// a spawn's placement of each new piece around the spawner
	inline void Place(const Spawn &sp, Particle *r)
	{
		const std::vector<Val> &a = sp.place.a;
		switch (sp.place.op)
		{
		case CIRCLE_DROP: // angle min / max, drop min / max / den, radius num / den / max
		{
			const fxp::Range angle = { (int16_t)V(a[0]), (int16_t)V(a[1]) };
			const fxp::RandomFraction drop = { (int16_t)V(a[2]), (int16_t)V(a[3]), (int16_t)V(a[4]) };
			const fxp::Scaled radius = { (int16_t)V(a[5]), (int16_t)V(a[6]), (int16_t)V(a[7]) };
			const int32_t angle_rolled = angle.roll(CrtRand());
			Particle *m = (Particle *)SpawnTask(sp.task, r);
			CopyAnchorXZFromSource(m, m->h.pos);
			m->h.pos[1] = r->h.pos[1];
			int32_t d = (int32_t)r->h.pos[1] - (int32_t)(int16_t)BoundsMaxWorldY(r);
			d = mul32(d, drop.roll(CrtRand()));
			m->h.pos[1] = (int16_t)(m->h.pos[1] + d / -drop.den);
			m->radius = radius.of((int16_t)BoundsRadius(r));
			FX_NOTE("mote circle radius", m->radius);
			FX_NOTE("mote drop", d / -drop.den);
			OnCircle(m->h.pos, m->radius, angle_rolled);
			memcpy(m->vel, r->vel, 8);
			break;
		}
		case GLINT: // pool, ticks, grow w / h, shrink w / h, centre r / g / b, tip r / g / b, spin
		{
			fxp::GlintStyle style;
			style.ticks = (int16_t)V(a[1]);
			style.grow = { (int16_t)V(a[2]), (int16_t)V(a[3]) };
			style.shrink = { (int16_t)V(a[4]), (int16_t)V(a[5]) };
			for (int k = 0; k < 3; k++) style.centre_step[k] = (uint8_t)V(a[6 + k]);
			for (int k = 0; k < 3; k++) style.tip_step[k] = (uint8_t)V(a[9 + k]);
			style.spin = (int16_t)V(a[12]);
			SpawnGlint((TaskQueue *)g_program->pools[V(a[0])].queue, r, Mem("packet_cursor"), style);
			break;
		}
		default: SpawnTask(sp.task, r); break;   // at_parent: the new node takes the spawner's place
		}
	}

	inline void DrawOne(const Draw &d, Particle *p)
	{
		const std::vector<Val> &a = d.draw.a;
		const bool hidden = (p->h.flags & 4) != 0;
		switch (d.draw.op)
		{
		case SPRITE: // r, g, b, size
		{
			const fxp::Colour colour = { (uint8_t)V(a[0]), (uint8_t)V(a[1]), (uint8_t)V(a[2]), 0 };
			parts::DrawSprite(p->h.pos, p->seq, p->frame, p->shade, hidden, colour, (int16_t)V(a[3]), PacketCursor());
			break;
		}
		case GROUND_FLIPBOOK: // sequence, tilt, height, frame, grey start, fade a tick
		{
			// the 4th byte is the high byte of the task argument (the node address) the colour is written
			// over on the original's stack
			const uint32_t colour = FadingGrey((uint8_t)V(a[4]), (uint8_t)V(a[5]), p->h.counter, (uint32_t)p & 0xFF000000u);
			DrawGroundFlipbook(p->h.pos, hidden, fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), (int16_t)V(a[1]),
			                   (int16_t)V(a[2]), (int16_t)V(a[3]), colour, PacketCursor());
			break;
		}
		case PROJECTOR_OVERLAY: // image x, y, palette x, y, width, height, skip back faces
			Overlay().offset[1] = p->h.pos[1];
			overlay::SetOverlayTexturePage(&Overlay(), p->h.pos, V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]), V(a[5]));
			overlay::DrawTargetModelWithOverlay(&Overlay(), V(a[6]) != 0);
			break;
		default: break;
		}
	}

	// ------------------------------------------------------------------
	// A task's tick
	// ------------------------------------------------------------------
	inline uint32_t __cdecl RunTask(int k, TaskNode *n)
	{
		const Task &t = g_program->tasks[k];
		FxNode *h = (FxNode *)n;
		Particle *p = (Particle *)n;
		for (const Step &s : t.every_tick) Act(s, n);
		if (h->phase >= 0 && h->phase < (int)t.phases.size())
		{
			const Phase &ph = t.phases[h->phase];
			for (const Step &s : ph.each_tick) Act(s, n);
			if (Holds(ph.wait, n))
			{
				for (const Step &s : ph.act) Act(s, n);
				h->phase++;
			}
		}
		if (t.motion.op == HELIX) // steps per tick, angle a step
		{
			const int32_t substeps = V(t.motion.a[0]);
			for (uint32_t s = 0; s < (uint32_t)substeps; s++)
			{
				HelixPlace(p->h.pos, p->angle, p->center, p->vel[1], p->radius, (uint32_t)(uint16_t)(h->counter * substeps) + s,
				           (int16_t)V(t.motion.a[1]));
				for (const Spawn &sp : t.step_spawns)
				{
					const fxp::Window w = { (int16_t)V(sp.first), (int16_t)V(sp.last) };
					if ((h->flags & sp.gate) && w.has(h->counter)) Place(sp, p);
				}
			}
		}
		for (const Spawn &sp : t.spawns)
		{
			if (sp.gate && !(h->flags & sp.gate)) continue;
			const int16_t c = h->counter;
			const fxp::Window w = { (int16_t)V(sp.first), (int16_t)V(sp.last) };
			if (!w.has(c)) continue;
			fxp::Schedule schedule;
			for (int j = 0; j < 4; j++)
			{
				schedule.from[j] = (int16_t)V(sp.schedule[2 * j]);
				schedule.count[j] = (int16_t)V(sp.schedule[2 * j + 1]);
			}
			for (int32_t m = schedule.at(c); m > 0; m--) Place(sp, p);
		}
		for (const Step &s : t.events) Act(s, n);
		for (const Draw &d : t.draws)
		{
			if (d.gate && !(h->flags & d.gate)) continue;
			if (d.limited && !(h->counter < V(d.below))) continue;
			FX_PART(d.tag);
			DrawOne(d, p);
		}
		h->counter++;
		return EndWhenDone(h);
	}

	// ------------------------------------------------------------------
	// The per-action director, the setup, the file loader
	// ------------------------------------------------------------------
	static const uint32_t CAM_SNAPSHOT = 0x2793E58;       // Effect_SharedCamMatrixSnapshot

	inline void DirectorPhase(RootNode *r)
	{
		switch (r->h.phase)
		{
		case 0:
		case 1:
			r->h.phase++;
			break;
		case 2: // children gone
			if (r->h.children == 0) r->h.phase++;
			break;
		case 3: // the spawned task of the current action
			r->busy = 1;
			SpawnTask(g_program->director_spawns, r);
			r->h.phase++;
			break;
		case 4: // when it is over, the next action (back to 3) or on
			if (r->busy == 0)
			{
				const int8_t a = r->h.action;
				if ((int16_t)a < r->last_action)
				{
					r->h.action = (int8_t)(a + 1);
					r->h.line++;
					r->h.phase--;
				}
				else r->h.phase++;
			}
			break;
		case 5:
			r->h.phase++;
			break;
		case 6: // every queue empty
			if (r->alive == 0) r->h.phase++;
			break;
		case 7:
		case 8:
			r->h.phase++;
			break;
		case 9: // done
			*(uint8_t *)&r->h.flags |= 1;
			r->h.phase++;
			break;
		default: break;
		}
	}

	inline uint32_t __cdecl DirectorTask(TaskNode *n)
	{
		RootNode *r = (RootNode *)n;
		memcpy((void *)CAM_SNAPSHOT, &Camera(), 0x20);
		var<uint32_t>(Mem("cam_ptr_a")) = CAM_SNAPSHOT;
		var<uint32_t>(Mem("cam_ptr_b")) = CAM_SNAPSHOT;
		if (r->tick & 1)
		{
			PacketCursor() = var<uint32_t>(Mem("arena_a"));
			var<uint32_t>(Mem("packet_limit")) = var<uint32_t>(Mem("limit_a"));
		}
		else
		{
			PacketCursor() = var<uint32_t>(Mem("arena_b"));
			var<uint32_t>(Mem("packet_limit")) = var<uint32_t>(Mem("limit_b"));
		}
		UpdateTargetPosFromBones(r);
		DirectorPhase(r);
		r->alive = 0;
		for (const Pool &pool : g_program->pools)
		{
			if (pool.tag >= 0) FX_PART(pool.tag);
			r->alive = (int16_t)(r->alive + ExecuteTaskQueue((TaskQueue *)pool.queue));
			if (pool.tag >= 0) FX_PART(0);
		}
		r->tick++;
		r->h.counter++;
		return EndWhenDone(&r->h);
	}

	inline uint32_t __cdecl FileLoader()
	{
		Program &g = *g_program;
		fxp::FileName name = {};
		if (g.texture_param >= 0) strncpy(name.name, g.params[g.texture_param].text.c_str(), sizeof(name.name) - 1);
		const uint32_t file = IO_GetFile_MAGIC(fxp::file(name, (const char *)g.texture_name));
		var<uint32_t>(Mem("texture_file")) = file;
		return file;
	}

	inline TaskQueue *__cdecl Setup(CastContext *ctx)
	{
		Program &g = *g_program;
		var<uint32_t>(Mem("init_flag_a")) = 0;
		var<uint32_t>(Mem("init_flag_b")) = 0;
		TaskQueue *root_queue = (TaskQueue *)Mem("root_queue");
		InitTaskQueuePool(root_queue, (void *)Mem("root_pool"), 0x64, 2);
		RootNode *r = (RootNode *)AddEffectTask(root_queue, g.root ? g.root : (uint32_t)DirectorTask, 0x64, nullptr);
		const ActionData *a = ctx->actions + r->h.action;
		r->h.ctx = ctx;
		r->h.attacker = a->attacker;
		r->h.phase = 0;
		r->h.slot = a->targets[TARGET_STRIDE * r->h.target];
		r->target_count = ctx->actions[0].target_count;
		r->last_action = ctx->actions[0].last_action;
		r->h.last = (uint8_t)(r->target_count - 1);
		if ((int16_t)r->h.last < r->last_action) r->h.last = (uint8_t)r->last_action;
		if (!(ctx->flags & 1))
		{
			PlayCameraAnimation((const void *)g.camera);
			QueueTimUpload(var<uint32_t>(Mem("texture_file")));
		}
		const uint32_t file = var<uint32_t>(Mem("texture_file"));
		var<uint32_t>(Mem("arena_a")) = file;
		var<uint32_t>(Mem("limit_a")) = file + 0x10000;
		var<uint32_t>(Mem("arena_b")) = file + 0x10000;
		var<uint32_t>(Mem("arena_top")) = file + 0x20000;
		var<uint32_t>(Mem("limit_b")) = file + 0x20000;
		for (const Pool &pool : g.pools) InitTaskQueuePool((TaskQueue *)pool.queue, (void *)pool.storage, pool.size, pool.count);
		return root_queue;
	}

	// ------------------------------------------------------------------
	// Loading
	// ------------------------------------------------------------------
	inline Val ParseVal(const std::string &token)
	{
		Val v;
		if (!token.empty() && token[0] == '$') { v.param = true; v.v = atoi(token.c_str() + 1); }
		else v.v = (int32_t)strtoll(token.c_str(), nullptr, 0);
		return v;
	}
	inline Step ParseStep(const std::vector<std::string> &w, size_t from, std::string *error)
	{
		Step s;
		if (from >= w.size()) return s;
		auto it = OPS.find(w[from]);
		if (it == OPS.end()) { *error = "unknown operation " + w[from]; return s; }
		s.op = it->second;
		for (size_t k = from + 1; k < w.size(); k++) s.a.push_back(ParseVal(w[k]));
		return s;
	}

	// the program in `path` (Fujin/effectprogram.py writes it); "" when it loaded, else what is wrong
	inline std::string Load(const char *path, Program &g)
	{
		FILE *f = fopen(path, "r");
		if (!f) return std::string("cannot read ") + path;
		std::string error;
		char line[4096];
		int number = 0;
		Task *task = nullptr;
		while (error.empty() && fgets(line, sizeof(line), f))
		{
			number++;
			std::vector<std::string> w;
			for (char *t = strtok(line, " \t\r\n"); t; t = strtok(nullptr, " \t\r\n")) w.push_back(t);
			if (w.empty() || w[0][0] == '#') continue;
			const std::string &d = w[0];
			auto need = [&](size_t n) { if (w.size() < n) error = "line " + std::to_string(number) + ": " + d + " needs more"; return error.empty(); };
			if (d == "program" && need(3)) { g.effect = atoi(w[1].c_str()); g.name = w[2]; }
			else if (d == "function" && need(3))
			{
				const uint32_t at = (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
				if (w[1] == "file_loader") g.file_loader = at;
				else if (w[1] == "setup") g.setup = at;
				else if (w[1] == "root") g.root = at;
			}
			else if (d == "memory" && need(3)) g.memory[w[1]] = (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
			else if (d == "texture" && need(3)) { g.texture_name = (uint32_t)strtoul(w[1].c_str(), nullptr, 0); g.texture_param = atoi(w[2].c_str()); }
			else if (d == "camera" && need(2)) g.camera = (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
			else if (d == "pool" && need(6))
				g.pools.push_back({ (uint32_t)strtoul(w[1].c_str(), nullptr, 0), (uint32_t)strtoul(w[2].c_str(), nullptr, 0),
				                    atoi(w[3].c_str()), atoi(w[4].c_str()), atoi(w[5].c_str()) });
			else if (d == "director" && need(3)) g.director_spawns = atoi(w[2].c_str());
			else if (d == "param" && need(5))
			{
				Param p;
				p.key = w[1];
				p.type = w[2];
				if (p.type == "file") p.text = w[3] == "-" ? "" : w[3];
				else
				{
					p.value = as_type(p.type, (int32_t)strtoll(w[3].c_str(), nullptr, 0));
					p.game = as_type(p.type, (int32_t)strtoll(w[4].c_str(), nullptr, 0));
				}
				g.params.push_back(p);
			}
			else if (d == "task" && need(5))
			{
				g.tasks.push_back({});
				task = &g.tasks.back();
				task->key = w[1];
				task->pool = atoi(w[2].c_str());
				task->function = (uint32_t)strtoul(w[3].c_str(), nullptr, 0);
				task->size = atoi(w[4].c_str());
			}
			else if (!task) error = "line " + std::to_string(number) + ": " + d + " outside a task";
			else if (d == "tick") task->every_tick.push_back(ParseStep(w, 1, &error));
			else if (d == "phase") task->phases.push_back({});
			else if (task->phases.empty() && (d == "phase_tick" || d == "wait" || d == "do")) error = "line " + std::to_string(number) + ": " + d + " outside a phase";
			else if (d == "phase_tick") task->phases.back().each_tick.push_back(ParseStep(w, 1, &error));
			else if (d == "wait") task->phases.back().wait = ParseStep(w, 1, &error);
			else if (d == "do") task->phases.back().act.push_back(ParseStep(w, 1, &error));
			else if (d == "motion") task->motion = ParseStep(w, 1, &error);
			else if (d == "step_spawn" && need(5))
			{
				Spawn sp;
				sp.task = atoi(w[1].c_str());
				sp.gate = atoi(w[2].c_str());
				sp.first = ParseVal(w[3]);
				sp.last = ParseVal(w[4]);
				sp.place = ParseStep(w, 5, &error);
				task->step_spawns.push_back(sp);
			}
			else if (d == "spawn" && need(14))
			{
				Spawn sp;
				sp.task = atoi(w[1].c_str());
				sp.gate = atoi(w[2].c_str());
				sp.first = ParseVal(w[3]);
				sp.last = ParseVal(w[4]);
				for (int j = 0; j < 8; j++) sp.schedule[j] = ParseVal(w[5 + j]);
				sp.place = ParseStep(w, 13, &error);
				task->spawns.push_back(sp);
			}
			else if (d == "event") task->events.push_back(ParseStep(w, 1, &error));
			else if (d == "draw" && need(5))
			{
				Draw dr;
				dr.tag = atoi(w[1].c_str());
				dr.gate = atoi(w[2].c_str());
				dr.limited = w[3] != "-";
				if (dr.limited) dr.below = ParseVal(w[3]);
				dr.draw = ParseStep(w, 4, &error);
				task->draws.push_back(dr);
			}
			else if (error.empty()) error = "line " + std::to_string(number) + ": unknown " + d;
		}
		fclose(f);
		if (error.empty() && (int)g.tasks.size() > (int)(sizeof(THUNKS) / sizeof(THUNKS[0]))) error = "too many tasks";
		if (error.empty() && (g.director_spawns < 0 || g.director_spawns >= (int)g.tasks.size())) error = "the director spawns no task";
		return error;
	}

	// the parameter `key` set to `text` (a number, or a file name); false when there is none
	inline bool SetParam(Program &g, const char *key, const char *text)
	{
		for (Param &p : g.params)
			if (p.key == key)
			{
				if (p.type == "file") p.text = text;
				else p.value = as_type(p.type, (int32_t)strtoll(text, nullptr, 0));
				return true;
			}
		return false;
	}
}
