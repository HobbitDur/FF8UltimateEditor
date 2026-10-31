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
// A task's node is the effect library's (the heal ring's nodes: FxNode, linked to their parent) or
// a plain one (an engine queue node and the fields the description lists: counter, position,
// size, table point, targets, layout), whose spawns can come every n ticks and draws can be prim
// layouts (fx_layouts.h). A task ends when it is done (effect nodes) or by its end condition.
//
// The director (the root task), the setup and the file loader are of one of two kinds: the effect
// library's per-action director (one emitter per action, in turn, until every queue is empty) or
// a master (Hypnotize's): it alternates two packet arenas of the magic buffer, sets up the pools
// at its start tick, starts one task with the targets of action 0 and ends when every queue is
// empty.
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
#include "fx_layouts.h"

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
	struct Spawn { int task = -1; int gate = 0; Val first, last; Val schedule[8]; bool every_kind = false; Val every; Step place; };
	enum Limit { NO_LIMIT, BELOW, AT_MOST };
	struct Draw { int tag = 0; int gate = 0; int limit = NO_LIMIT; Val value; Step draw; };
	// a plain node's fields (offsets in the node; -1: none)
	enum Field { F_COUNTER, F_POS, F_SCALE, F_POINT, F_TARGETS, F_LAYOUT, FIELD_COUNT };
	static const char *const FIELD_NAMES[FIELD_COUNT] = { "counter", "pos", "scale", "point", "targets", "layout" };
	struct Task
	{
		std::string key;
		int pool = 0, size = 0;
		uint32_t function = 0;                    // the original it stands in for (0: a new task)
		bool plain = false, draws_first = false;
		int field[FIELD_COUNT] = { -1, -1, -1, -1, -1, -1 };
		int layout_size = 0;
		Step end;                                 // a plain node's end (after its counter)
		std::vector<Step> every_tick;
		std::vector<Phase> phases;
		Step motion;
		std::vector<Spawn> step_spawns, spawns;
		std::vector<Step> events;
		std::vector<Draw> draws;
	};
	struct Pool { uint32_t queue = 0, storage = 0; int size = 0, count = 0, tag = -1, base = 0; };   // base 1: storage in the magic buffer
	enum Director { PER_ACTION, MASTER };
	struct Program
	{
		int effect = 0;
		std::string name;
		std::map<std::string, uint32_t> memory;
		uint32_t file_loader = 0, setup = 0, root = 0, camera = 0, texture_name = 0;
		uint32_t director_fn = 0;                       // the director task the setup starts (0: DirectorTask)
		int texture_param = -1, director_spawns = -1;
		int director = PER_ACTION, director_start = 1;
		Step director_place;
		uint32_t arena_a = 0, arena_b = 0, morph = 0;   // in the magic buffer
		std::vector<Pool> pools;
		std::vector<Param> params;
		std::vector<Task> tasks;
	};

	enum Op
	{
		NONE,
		// actions
		FOLLOW_TARGET, SPAWN, HEAL, DONE, SPAWNING, OVERLAY, SEQUENCE, FLIPBOOK, HELIX_START, OVERLAY_START,
		HIDE_TARGET, SHOW_TARGET, UNBLOCK_DIRECTOR, VELOCITY_ROLL, VELOCITY_RISE, DRIFT, SOUND_AT, HEAL_ALL_AT,
		// conditions
		TICK_AT_LEAST, FLIPBOOK_END, LAYOUT_END,
		// motions
		HELIX,
		// placements
		CIRCLE_DROP, GLINT, AT_PARENT, TABLE_POINT, RANDOM_TARGET_BONE, RANDOM_TARGET_POINT, ACTION_TARGETS,
		// draws
		SPRITE, GROUND_FLIPBOOK, PROJECTOR_OVERLAY, LAYOUT_ON_SCREEN, LAYOUT_AT_CASTER_BONE, LAYOUT_SCALED, SEQUENCE_SPRITE,
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
		{ "heal_all_at", HEAL_ALL_AT }, { "layout_end", LAYOUT_END }, { "table_point", TABLE_POINT },
		{ "random_target_bone", RANDOM_TARGET_BONE }, { "random_target_point", RANDOM_TARGET_POINT },
		{ "action_targets", ACTION_TARGETS }, { "layout_on_screen", LAYOUT_ON_SCREEN },
		{ "layout_at_caster_bone", LAYOUT_AT_CASTER_BONE }, { "layout_scaled", LAYOUT_SCALED },
		{ "sequence_sprite", SEQUENCE_SPRITE },
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
	inline uint32_t &MagicBuffer() { return var<uint32_t>(Mem("magic_buffer")); }
	inline CastContext *&Ctx() { return var<CastContext *>(Mem("ctx")); }
	inline uint8_t *&Caster() { return var<uint8_t *>(Mem("caster")); }

	// a plain node's field (nullptr: the task has none)
	template<typename T> inline T *Fld(const Task &t, void *n, int f) { return t.field[f] < 0 ? nullptr : (T *)((uint8_t *)n + t.field[f]); }
	inline int16_t *CounterOf(const Task &t, void *n) { return t.plain ? Fld<int16_t>(t, n, F_COUNTER) : &((FxNode *)n)->counter; }
	inline int32_t Tick(const Task &t, void *n) { const int16_t *c = CounterOf(t, n); return c ? *c : 0; }

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
	// a new node of task k: an effect node under `parent`, or a plain node (zeroed; nullptr when its
	// pool is full)
	inline FxNode *SpawnTask(int k, void *parent)
	{
		const Task &t = g_program->tasks[k];
		const Pool &pool = g_program->pools[t.pool];
		if (!t.plain) return AddEffectTask((TaskQueue *)pool.queue, TaskFunction(k), t.size, parent);
		TaskNode *n = AddTaskToQueue((TaskQueue *)pool.queue, TaskFunction(k));
		if (n) memset((uint8_t *)n + sizeof(TaskNode), 0, t.size - sizeof(TaskNode));
		return (FxNode *)n;
	}
	inline void DecodeLayout(const Task &t, void *n, uint32_t data) { layouts::DecodeModelPrimLayout(data, Fld<uint8_t>(t, n, F_LAYOUT), t.layout_size); }
	// a random entity of a plain node's targets field (count, then the entities)
	inline uint8_t *RandomTargetOf(const Task &t, void *n)
	{
		uint8_t *f = Fld<uint8_t>(t, n, F_TARGETS);
		return layouts::RandomEntity((uint8_t *const *)(f + 2), *(int16_t *)f);
	}

	// ------------------------------------------------------------------
	// Actions and conditions
	// ------------------------------------------------------------------
	inline void Act(const Task &t, const Step &s, TaskNode *n)
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
			if (Tick(t, n) == V(a[0])) BdPlaySE((const void *)fxp::sound((uint32_t)V(a[1]), (uint32_t)G(a[1])), 0, V(a[2]));
			break;
		case HEAL_ALL_AT: // tick: every target of action 0 takes the result
			if (Tick(t, n) == V(a[0])) ApplyActionResultToTargets(Ctx()->actions[0].targets, Ctx()->actions[0].target_count);
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

	// a plain node's placement (`from`: the spawning task, `n` its node; e: the spawn's number in
	// its window)
	inline void PlacePlain(const Spawn &sp, const Task &from, TaskNode *n, uint32_t e)
	{
		const std::vector<Val> &a = sp.place.a;
		const Task &t = g_program->tasks[sp.task];
		TaskNode *m = (TaskNode *)SpawnTask(sp.task, n);
		if (!m) return;
		switch (sp.place.op)
		{
		case TABLE_POINT: // table of points (x, y, z, bone), layouts, count: entry e of each
		{
			const uint32_t i = e % (uint32_t)V(a[2]);
			const uint32_t *table = (const uint32_t *)V(a[0]);
			uint32_t *point = Fld<uint32_t>(t, m, F_POINT);
			point[0] = table[2 * i];
			point[1] = table[2 * i + 1];
			DecodeLayout(t, m, ((const uint32_t *)V(a[1]))[i]);
			break;
		}
		case RANDOM_TARGET_BONE: // x spread min / max, size min / max, layouts, count
		{
			int16_t *pos = Fld<int16_t>(t, m, F_POS);
			layouts::RandomBonePoint(RandomTargetOf(from, n), pos);
			const fxp::Range spread = { (int16_t)V(a[0]), (int16_t)V(a[1]) }, scale = { (int16_t)V(a[2]), (int16_t)V(a[3]) };
			pos[0] = (int16_t)(pos[0] + spread.roll(CrtRand()));
			*Fld<int16_t>(t, m, F_SCALE) = (int16_t)scale.roll(CrtRand() >> 4);
			DecodeLayout(t, m, ((const uint32_t *)V(a[4]))[e % (uint32_t)V(a[5])]);
			break;
		}
		case RANDOM_TARGET_POINT: // bone, x min / max, y min / max, z min / max
		{
			int16_t *pos = Fld<int16_t>(t, m, F_POS);
			layouts::GetEffectSpawnPosition(RandomTargetOf(from, n), V(a[0]), 0, pos);
			const fxp::Range3 spread = { { (int16_t)V(a[1]), (int16_t)V(a[2]) }, { (int16_t)V(a[3]), (int16_t)V(a[4]) },
			                             { (int16_t)V(a[5]), (int16_t)V(a[6]) } };
			pos[0] = (int16_t)(pos[0] + spread.x.roll(CrtRand()));
			pos[1] = (int16_t)(pos[1] + spread.y.roll(CrtRand()));
			pos[2] = (int16_t)(pos[2] + spread.z.roll(CrtRand()));
			break;
		}
		default: break;
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

	// a plain node's draw; a layout's frames left go to `left`
	inline void DrawPlain(const Draw &d, const Task &t, TaskNode *n, int &left)
	{
		const std::vector<Val> &a = d.draw.a;
		layouts::PrimArg arg;
		arg.morph = MagicBuffer() + g_program->morph;
		arg.cursor = &PacketCursor();
		switch (d.draw.op)
		{
		case LAYOUT_ON_SCREEN: // basis (x H), depth (x H), offset scale (2^n), PSX pixels, prim depth: on the caster's screen point
		{
			int16_t pos[4];
			GetDefaultEffectPosition(Caster(), pos);
			layouts::ViewFrame(pos, V(a[0]), V(a[1]), V(a[2]), V(a[3]) != 0, &arg.m);
			arg.depth = V(a[4]);
			left = layouts::Play(Fld<uint8_t>(t, n, F_LAYOUT), &arg);
			break;
		}
		case LAYOUT_AT_CASTER_BONE: // prim depth: at the node's point of the caster's bones
		{
			int16_t pos[4];
			layouts::BonePoint(Caster(), Fld<int16_t>(t, n, F_POINT), pos);
			layouts::CameraRotation(&arg.m);
			layouts::CameraAnchor(pos, &arg.m);
			arg.depth = V(a[0]);
			left = layouts::Play(Fld<uint8_t>(t, n, F_LAYOUT), &arg);
			break;
		}
		case LAYOUT_SCALED: // prim depth: at the node's position, the camera's rotation scaled by its size
			layouts::ScaledCamera(*Fld<int16_t>(t, n, F_SCALE), &arg.m);
			layouts::CameraAnchor(Fld<int16_t>(t, n, F_POS), &arg.m);
			arg.depth = V(a[0]);
			left = layouts::Play(Fld<uint8_t>(t, n, F_LAYOUT), &arg);
			break;
		case SEQUENCE_SPRITE: // sequence, rotation a, b: frame = the counter, at the node's position
			layouts::DrawSequenceSprite(Fld<int16_t>(t, n, F_POS), fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])),
			                            (int16_t)Tick(t, n), V(a[1]), V(a[2]), PacketCursor());
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
		int left = 1;                             // the frames left of a layout drawn this tick
		auto draws = [&]()
		{
			for (const Draw &d : t.draws)
			{
				if (!t.plain && d.gate && !(h->flags & d.gate)) continue;
				if (d.limit == BELOW && !(Tick(t, n) < V(d.value))) continue;
				if (d.limit == AT_MOST && !((uint16_t)Tick(t, n) <= (uint16_t)V(d.value))) continue;
				FX_PART(d.tag);
				if (t.plain) DrawPlain(d, t, n, left);
				else DrawOne(d, p);
			}
		};
		for (const Step &s : t.every_tick) Act(t, s, n);
		if (!t.plain && h->phase >= 0 && h->phase < (int)t.phases.size())
		{
			const Phase &ph = t.phases[h->phase];
			for (const Step &s : ph.each_tick) Act(t, s, n);
			if (Holds(ph.wait, n))
			{
				for (const Step &s : ph.act) Act(t, s, n);
				h->phase++;
			}
		}
		if (t.draws_first) draws();
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
			if (!t.plain && sp.gate && !(h->flags & sp.gate)) continue;
			const int16_t c = (int16_t)Tick(t, n);
			const fxp::Window w = { (int16_t)V(sp.first), (int16_t)V(sp.last) };
			if (!w.has(c)) continue;
			const bool plain = sp.task >= 0 && g_program->tasks[sp.task].plain;
			if (sp.every_kind) // one every n ticks from the window's first
			{
				const int32_t every = V(sp.every);
				if (every <= 0 || (c - w.first) % every != 0) continue;
				const uint32_t e = (uint32_t)((c - w.first) / every);
				if (plain) PlacePlain(sp, t, n, e);
				else Place(sp, p);
				continue;
			}
			fxp::Schedule schedule;
			for (int j = 0; j < 4; j++)
			{
				schedule.from[j] = (int16_t)V(sp.schedule[2 * j]);
				schedule.count[j] = (int16_t)V(sp.schedule[2 * j + 1]);
			}
			for (int32_t m = schedule.at(c); m > 0; m--)
				if (plain) PlacePlain(sp, t, n, 0);
				else Place(sp, p);
		}
		for (const Step &s : t.events) Act(t, s, n);
		if (!t.draws_first) draws();
		if (int16_t *c = CounterOf(t, n)) (*c)++;
		if (!t.plain) return EndWhenDone(h);
		switch (t.end.op)
		{
		case TICK_AT_LEAST: return Tick(t, n) >= V(t.end.a[0]) ? TASK_END : 0;
		case LAYOUT_END: return left ? 0 : TASK_END;
		default: return 0;
		}
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

	inline uint32_t PerActionDirector(TaskNode *n)
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

	// the master (Hypnotize 0x6B1060): a node of 0x14 bytes
#pragma pack(push, 1)
	struct MasterNode
	{
		TaskNode hdr;
		int16_t counter;   // +0x0C
		uint8_t pad0E;
		uint8_t started;   // +0x0F pools set up
		uint32_t arena;    // +0x10 packet arena parity
	};
#pragma pack(pop)
	inline uint32_t PoolStorage(const Pool &pool) { return pool.base ? MagicBuffer() + pool.storage : pool.storage; }

	inline uint32_t MasterDirector(TaskNode *n)
	{
		Program &g = *g_program;
		MasterNode *m = (MasterNode *)n;
		if (m->arena)
		{
			PacketCursor() = MagicBuffer() + g.arena_a;
			m->arena = 0;
		}
		else
		{
			PacketCursor() = MagicBuffer() + g.arena_b;
			m->arena = 1;
		}
		if (m->counter == g.director_start && !m->started)
		{
			m->started = 1;
			for (const Pool &pool : g.pools) InitTaskQueuePool((TaskQueue *)pool.queue, (void *)PoolStorage(pool), pool.size, pool.count);
			// the started task with the targets of action 0 (count, entities) and its layout
			const Task &t = g.tasks[g.director_spawns];
			TaskNode *s = (TaskNode *)SpawnTask(g.director_spawns, nullptr);
			if (int16_t *targets = Fld<int16_t>(t, s, F_TARGETS))
			{
				targets[0] = (int16_t)Ctx()->actions[0].target_count;
				for (int32_t i = 0; i < targets[0]; i++)
					((uint8_t **)(targets + 1))[i] = Entity(Ctx()->actions[0].targets[i * TARGET_STRIDE]);
			}
			if (g.director_place.op == ACTION_TARGETS && t.field[F_LAYOUT] >= 0) DecodeLayout(t, s, (uint32_t)V(g.director_place.a[0]));
		}
		if (m->started)
		{
			bool alive = false;
			for (const Pool &pool : g.pools)
			{
				if (pool.tag >= 0) FX_PART(pool.tag);
				if (ExecuteTaskQueue((TaskQueue *)pool.queue)) alive = true;
				if (pool.tag >= 0) FX_PART(0);
			}
			FX_PART(0);
			if (!alive) return TASK_END;
		}
		m->counter++;
		return 0;
	}

	inline uint32_t __cdecl DirectorTask(TaskNode *n)
	{
		return g_program->director == MASTER ? MasterDirector(n) : PerActionDirector(n);
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

	// the master's setup (Hypnotize 0x6B0FE0): texture upload, the magic buffer, the cast, the
	// caster, the master node, the camera
	inline TaskQueue *MasterSetup(CastContext *ctx)
	{
		Program &g = *g_program;
		QueueTimUpload(var<uint32_t>(Mem("texture_file")));
		MagicBuffer() = layouts::MagicBuffer();
		Ctx() = ctx;
		Caster() = Entity(ctx->attacker);
		TaskQueue *root_queue = (TaskQueue *)Mem("root_queue");
		InitTaskQueuePool(root_queue, (void *)Mem("root_pool"), sizeof(MasterNode), 1);
		TaskNode *m = AddTaskToQueue(root_queue, g.root ? g.root : g.director_fn ? g.director_fn : (uint32_t)DirectorTask);
		Memset32(m + 1, 0, 2);
		PlayCameraAnimation((const void *)g.camera);
		return root_queue;
	}

	inline TaskQueue *__cdecl Setup(CastContext *ctx)
	{
		Program &g = *g_program;
		if (g.director == MASTER) return MasterSetup(ctx);
		var<uint32_t>(Mem("init_flag_a")) = 0;
		var<uint32_t>(Mem("init_flag_b")) = 0;
		TaskQueue *root_queue = (TaskQueue *)Mem("root_queue");
		InitTaskQueuePool(root_queue, (void *)Mem("root_pool"), 0x64, 2);
		RootNode *r = (RootNode *)AddEffectTask(root_queue, g.root ? g.root : g.director_fn ? g.director_fn : (uint32_t)DirectorTask, 0x64, nullptr);
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

	// the program `text` (Fujin/effectprogram.py writes it); "" when it parsed, else what is wrong
	inline std::string Parse(const std::string &text, Program &g)
	{
		std::string error;
		int number = 0;
		Task *task = nullptr;
		size_t at = 0;
		while (error.empty() && at < text.size())
		{
			size_t end = text.find('\n', at);
			if (end == std::string::npos) end = text.size();
			const std::string line = text.substr(at, end - at);
			at = end + 1;
			number++;
			std::vector<std::string> w;
			for (size_t i = 0; i < line.size();)
			{
				while (i < line.size() && strchr(" \t\r", line[i])) i++;
				size_t j = i;
				while (j < line.size() && !strchr(" \t\r", line[j])) j++;
				if (j > i) w.push_back(line.substr(i, j - i));
				i = j;
			}
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
				                    atoi(w[3].c_str()), atoi(w[4].c_str()), atoi(w[5].c_str()), w.size() > 6 ? atoi(w[6].c_str()) : 0 });
			else if (d == "magic_buffer" && need(4))
			{
				g.arena_a = (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
				g.arena_b = (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
				g.morph = (uint32_t)strtoul(w[3].c_str(), nullptr, 0);
			}
			else if (d == "director" && need(3))
			{
				g.director_spawns = atoi(w[2].c_str());
				if (w[1] == "master" && need(4))
				{
					g.director = MASTER;
					g.director_start = atoi(w[3].c_str());
					g.director_place = ParseStep(w, 4, &error);
				}
				else if (w[1] != "per_action") error = "line " + std::to_string(number) + ": unknown director " + w[1];
			}
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
			else if (d == "node" && need(2)) task->plain = w[1] == "plain";
			else if (d == "field" && need(4))
			{
				int f = 0;
				while (f < FIELD_COUNT && w[1] != FIELD_NAMES[f]) f++;
				if (f == FIELD_COUNT) error = "line " + std::to_string(number) + ": unknown field " + w[1];
				else
				{
					task->field[f] = atoi(w[2].c_str());
					if (f == F_LAYOUT) task->layout_size = atoi(w[3].c_str());
				}
			}
			else if (d == "order" && need(2)) task->draws_first = w[1] == "draws_first";
			else if (d == "end") task->end = ParseStep(w, 1, &error);
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
			else if (d == "spawn_every" && need(6))
			{
				Spawn sp;
				sp.task = atoi(w[1].c_str());
				sp.first = ParseVal(w[2]);
				sp.last = ParseVal(w[3]);
				sp.every_kind = true;
				sp.every = ParseVal(w[4]);
				sp.place = ParseStep(w, 5, &error);
				task->spawns.push_back(sp);
			}
			else if (d == "event") task->events.push_back(ParseStep(w, 1, &error));
			else if (d == "draw" && need(6))
			{
				Draw dr;
				dr.tag = atoi(w[1].c_str());
				dr.gate = atoi(w[2].c_str());
				dr.limit = w[3] == "below" ? BELOW : w[3] == "at_most" ? AT_MOST : NO_LIMIT;
				if (dr.limit != NO_LIMIT) dr.value = ParseVal(w[4]);
				dr.draw = ParseStep(w, 5, &error);
				task->draws.push_back(dr);
			}
			else if (error.empty()) error = "line " + std::to_string(number) + ": unknown " + d;
		}
		if (error.empty() && (int)g.tasks.size() > (int)(sizeof(THUNKS) / sizeof(THUNKS[0]))) error = "too many tasks";
		if (error.empty() && (g.director_spawns < 0 || g.director_spawns >= (int)g.tasks.size())) error = "the director spawns no task";
		for (size_t k = 0; error.empty() && k < g.tasks.size(); k++)
		{
			const Task &t = g.tasks[k];
			for (int f = 0; f < FIELD_COUNT; f++)
				if (t.field[f] >= 0 && !t.plain) error = "task " + t.key + ": fields on an effect node";
			for (const Spawn &sp : t.spawns)
				if (sp.task >= (int)g.tasks.size() || (sp.task < 0 && sp.place.op != GLINT)) error = "task " + t.key + ": a spawn of no task";
		}
		return error;
	}

	// the program in `path`
	inline std::string Load(const char *path, Program &g)
	{
		FILE *f = fopen(path, "rb");
		if (!f) return std::string("cannot read ") + path;
		std::string text;
		char block[4096];
		for (size_t n; (n = fread(block, 1, sizeof(block), f)) > 0;) text.append(block, n);
		fclose(f);
		return Parse(text, g);
	}

	// the program run by itself, as a new effect: no exe function stands in for it
	inline void Detach(Program &g)
	{
		g.file_loader = g.setup = g.root = 0;
		for (Task &t : g.tasks) t.function = 0;
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
