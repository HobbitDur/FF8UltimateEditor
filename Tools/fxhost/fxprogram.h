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
// size, table point, targets, layout, anchor), whose spawns can come every n ticks and draws can
// be prim layouts (fx_layouts.h). A task ends when it is done (effect nodes) or by its end
// condition, then runs its at-end actions.
//
// The director (the root task), the setup and the file loader are of one of four kinds: the effect
// library's per-action director (one emitter per action, in turn, until every queue is empty), a
// chain (Fire's: one director task per action, each starting the next one's, the root alternating
// two packet arenas by its counter), a cycle (Silence's: one task per action, every n ticks, on the
// action's target) or a master
// (Hypnotize's, Antidote's): it alternates two packet arenas of the magic buffer, sets up
// the pools at its start tick, starts one task (with the targets of action 0, or at target 0's
// anchor), runs its own events on its counter before or after its queues (and, for Echo Screen,
// its own camera matrix every tick) and ends when every queue is empty.
//
// A program can stand in for an effect of the exe (its `function` addresses: the recorder jumps
// from each original to the program's thunk) or be a new one (no address: the thunks are the
// task functions). It works in its exe copy's memory (`memory` addresses) or in its own (`own`
// sizes, and pools whose queue and storage are `own`): one zeroed block the program holds. The
// data it reads (sequences, sounds, layouts, tables, its texture name, its camera) is the exe's
// (addresses) or its own (`data` lines, hex bytes; `data_pointers`, tables of their addresses),
// named @key wherever a number goes.

#pragma once

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <map>
#include <string>
#include <vector>

#include "mag_heal_ring_code.h"
#include "fx_layouts.h"
#include "fx_sway.h"
#include "fx_ripple.h"
#include "fx_barrier.h"
#include "fx_rays.h"
#include "fx_ribbon.h"
#include "fx_flames.h"
#include "fx_bolt.h"
#include "fx_runes.h"
#include "fx_revive.h"
#if __has_include("fx_actors.h")
#include "fx_actors.h"   // the act family's actor system (FFNx sources with it: fx_actors.cpp and act_engine.cpp built in)
#define FXPROG_ACTORS 1
#endif

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

	struct Val { bool param = false; int32_t v = 0; bool neg = false; };   // (neg: a parameter's value negated, "-$n")
	struct Param { std::string key, type, text; int32_t value = 0, game = 0; };
	struct Step { int op = 0; std::vector<Val> a; };
	struct Phase { std::vector<Step> each_tick; Step wait; std::vector<Step> act; };
	struct Spawn { int task = -1; int gate = 0; Val first, last; Val schedule[8]; bool every_kind = false; Val every; Step place; std::vector<Step> init; };   // init: actions on the new node (child.)
	enum Limit { NO_LIMIT, BELOW, AT_MOST, AT_LEAST, WITHIN };
	struct Draw { int tag = 0; int gate = 0; int limit = NO_LIMIT; Val value, count; Step draw; Step when; };   // (count: WITHIN's; when: a condition on the node)
	// a plain node's fields (offsets in the node; -1: none)
	enum Field { F_COUNTER, F_POS, F_SCALE, F_POINT, F_TARGETS, F_LAYOUT, F_ANCHOR, F_ACTION, F_ENTITY, F_LAYOUT_B, F_SPAWN, F_END, F_SEQ, F_RADIUS, F_ANGLE, F_SPEED, F_FADE,
	             F_LEAF, F_COLOUR, F_RIPPLE, F_SPARK, F_BARRIER, F_ORBIT, F_GROWTH, F_RAYS, F_RIBBON, F_MOTE, F_DRAWN,
	             F_SLOT, F_CHAIN, F_DELAY, F_LIFE, F_FLAME, F_EMBER, F_FIRE_SPARK, FIELD_COUNT };
	static const char *const FIELD_NAMES[FIELD_COUNT] = { "counter", "pos", "scale", "point", "targets", "layout", "anchor", "action", "entity",
	                                                      "layout_b", "spawn", "end", "seq", "radius", "angle", "speed", "fade",
	                                                      "leaf", "colour", "ripple", "spark", "barrier", "orbit", "growth",
	                                                      "rays", "ribbon", "mote", "drawn",
	                                                      "slot", "chain", "delay", "life", "flame", "ember", "fire_spark" };
	struct Task
	{
		std::string key;
		int pool = 0, size = 0;
		uint32_t function = 0;                    // the original it stands in for (0: a new task)
		uint32_t code = 0;                        // the original it mirrors, kept in a copy (a port module's code spawning it finds it)
		uint32_t native = 0;                      // its body the port of this original (a port module's task, Draw's emitter)
		bool plain = false, draws_first = false;
		int field[FIELD_COUNT] = { -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
		                           -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1 };
		// while the battle only draws (DrawOnly): NO_DRAW_ONLY runs as always, DRAW_ONLY_SKIP does
		// nothing (Fire's directors), DRAW_ONLY_DRAWS stops after its first draws (Fire's flames)
		int draw_only = 0;
		Step hold;                                // after its every-tick actions: when it holds, the tick stops there
		int layout_size = 0, layout_b_size = 0;
		Step end;                                 // a plain node's end (after its counter)
		std::vector<Step> at_end;                 // actions when it ends
		std::vector<Step> every_tick;
		std::vector<Phase> phases;
		std::vector<Step> moves;                  // after its phase, before its draws and spawns (Double's motion)
		Step motion;
		std::vector<Spawn> step_spawns, spawns;
		std::vector<Step> events, after;          // after: once its draws are done
		std::vector<Draw> draws;
	};
	struct Pool
	{
		uint32_t queue = 0, storage = 0;
		int size = 0, count = 0, tag = -1, base = 0;   // base 1: storage in the magic buffer
		bool own_queue = false, own_storage = false;  // allocated in the program's own memory
		uint32_t before = 0;                          // a module function the master calls before this queue runs (Stare's view axes)
		std::vector<std::string> before_args;         // its arguments: numbers, @memory names (a copy's moved)
	};
	enum Director { PER_ACTION, MASTER, CYCLE, CHAIN, PORT };
	// a value written into data before every cast (an actor definition's field: the act family's)
	struct Patch { uint32_t at = 0; int type = 0; Val value; };
	enum DrawOnlyKind { NO_DRAW_ONLY, DRAW_ONLY_SKIP, DRAW_ONLY_DRAWS };
	struct Program
	{
		int effect = 0;
		std::string name;
		std::map<std::string, uint32_t> memory;
		uint32_t file_loader = 0, setup = 0, root = 0, camera = 0, texture_name = 0;
		uint32_t texture_data = 0;                      // a TIM the setup uploads as it is (Thunder's exe data): the file loader loads nothing
		struct ExtraFile { std::string memory; uint32_t name = 0; bool first = false; };
		std::vector<ExtraFile> files;                   // more files the file loader loads into memory words (Devour's pictures), in order
		uint32_t director_fn = 0;                       // the director task the setup starts (0: DirectorTask)
		int texture_param = -1, director_spawns = -1;
		int director = PER_ACTION, director_start = 1;
		int director_single = -1;                       // CHAIN: the lone target's director task (director_spawns: several targets')
		bool director_short = false;                    // PER_ACTION: Double's short root (4 phases, arenas of the magic buffer) and setup
		bool short_upload_always = false;               // its setup uploads the texture even when the cast repeats (Phoenix Down's)
		uint32_t arena_size = 0x10000;                  // PER_ACTION: each of its two packet arenas in the texture file (Mega Phoenix: 0xA000)
		bool per_target = false;                        // PER_ACTION: its task for each target of the action, in turn (Mega Phoenix's), not each action
		bool release_file = false;                      // PER_ACTION: at its end its file's release asked and waited for (Doom's)
		uint32_t port_setup = 0, port_loader = 0, port_root = 0;   // PORT: the port's (originals: own::find)
		bool port_setup_exe = false;                    // PORT: the module's own setup called (shared memory: the cinematic engine's), its root re-pointed
		// PER_ACTION, the act family's master (Mega Phoenix 0x8CE4F0): once the children are gone (state 2) room
		// carved from the arena top for memory words (act_pools: name, bytes), cleared, u16 words zeroed
		// (act_zero), the stage fade in task; after the last action, act_wait ticks, then the stage fade
		// out task; u16 words cleared every tick before the queues (act_clear)
		int act_stage_in = -1, act_stage_out = -1;
		Val act_wait;
		std::vector<std::pair<std::string, uint32_t>> act_pools;
		std::vector<std::string> act_zero, act_clear;
		// after the stage in task, functions its master calls once (act_call: the function, its arguments -
		// numbers, @caster: the caster's entity, @name: a memory word's address; Quistis' cast animation)
		struct ActCall { uint32_t fn; std::vector<std::string> args; };
		std::vector<ActCall> act_calls;
		// after the last action, the module's own master states from its state 6 on (act_tail: Ultimecia's final
		// form dies - its file load, the fanfare hand-over, the music, the unload waits, its finish), called with
		// the root as its master calls them: each moves the root's state (+0x29) on itself
		std::vector<uint32_t> act_tail;
		int act_part = 0, act_first_part = 0;            // the lab's parts: the actor system's, its definition 0's (k: + k)
		std::vector<Patch> patches;                     // written by the setup, before anything runs
		// a port module whose code runs (Doom's kind: its state functions called from the phases, its own tasks
		// spawned by it): its effect, its memory [module_lo, + module_size) - in a copy, one block of the program's
		// (module_own: every address in it moved by module_reloc) - and the data words pointing into it (G index, word)
		int module = 0;
		uint32_t module_lo = 0, module_size = 0, module_reloc = 0;
		bool module_own = false;
		std::vector<std::pair<int, uint32_t>> module_pointers;
		std::vector<uint8_t> module_block;
#ifdef FXPROG_ACTORS
		ff8fx::act::Mod module_mod = {};
		bool module_ready = false;
		uint32_t module_words[8] = {};
		ff8fx::act::actors::Mem actor_mem = {};         // the actor system's memory (its own or the copy's) and descriptor
		ff8fx::act::Mod actor_mod = {};
		bool actors_ready = false;
#endif
		Val director_every;                             // CYCLE: one task per action every this many ticks
		Step director_place;
		std::vector<Step> director_events;              // the master's, on its counter, after its queues...
		std::vector<Step> director_events_first;        // ...or before them
		bool camera_matrix = false;                     // the master's own camera matrix (memory camera_matrix), every tick
		bool master_setup = false;                      // a cycle director set up as the master is (Petrify Stare's: the caster kept, the camera always)
		bool seed_shared_rand = false;                  // the setup seeds the effects' shared LCG with a CRT rand (Reflect's)
		int director_spawn_tick = 1;                    // the cycle director's counter it starts a task at (Reflect: 0)
		uint32_t arena_a = 0, arena_b = 0, morph = 0;   // in the magic buffer
		std::vector<std::pair<std::string, uint32_t>> own;   // memory of its own: name, size
		std::vector<uint8_t> block;                     // that memory (never resized once allocated)
		std::map<std::string, uint32_t> data;           // its own data: key -> address
		std::vector<std::vector<uint8_t>> blobs;        // that data (each buffer stays where it is)
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
		HEAL_FIRST_TARGET, ANCHOR_AT_BONE, SOUND_3D_AT, HEAL_ACTION_AT, UNMARK_TARGET, ANCHOR_AT_POSITION,
		HEAL_ACTION, SCREEN_FADE_AT, BLINK_TARGET, SCREEN_FLASH_CURVE, SCREEN_FLASH_OFF, SPIN, WHIRL_LEAF_MOVE,
		FLASH_LEVEL_RAISE, FOLLOW_BONE, SOUND_3D_AT_POSITION, FLASH_LEVEL_CLEAR, SCREEN_FLASH_LEVEL, POINT_AT_POSITION,
		MARK_RING_FROM, UNMARK_RING, FLASH_LEVEL_HOLD, FLASH_LEVEL_SET, MARK_TARGET, TINT_TARGET, SPARK_STEP, SPARK_MOVE,
		BARRIER_FRAME, BARRIER_CENTER, DEAD_BEAMS, ORBIT_MOVE, GROWTH_STEP, SPAWN_TO_FEET, RAY_SPAWN, MOTE_STEP,
		CHAIN_NEXT, RELEASE_TARGET, HEAL_ACTION_ALL_AT, SOUND_PAN_AT, EMBER_RISE, FIRE_SPARK_MOVE, CLAIM_TARGET,
		SPAWN_SIZE_WORD, SOUND_3D_AT_SPAWN,
		ADD, SET, COPY, FLAGS, SET_WHEN, ADD_WHEN, ADD_BELOW, ADD_VAR, SPIN_VAR, CIRCLE_PLACE, CIRCLE_PLACE_VAR, ANCHOR_XZ, ANCHOR_TOP,
		RAND_MASK, RAND_HOP, INDEX_TIMES, TICK_TIMES, TURNED_OFFSET, FADE_PULSE, GREY_PULSE, MORPH, SPAWN_WHEN, SPAWN_UNLESS_TARGET_BITS,
		SCREEN_FADE_WHEN, WRAP, REVIVE_RING_STEP, ACTOR_SETUP, ACTOR_STEP, STAGE_CLEAR, STAGE_FADE, CALL,
		// conditions
		TICK_AT_LEAST, FLIPBOOK_END, LAYOUT_END, TICK_ABOVE, TICK_AT_NODE_END, LEAF_GONE, SPARK_GONE, RAYS_DONE, RIBBON_DONE, MOTE_DONE, LIFE_OUT,
		VAR_AT_MOST, VAR_AT_LEAST, VAR_EQUALS, NEVER, AT_LEAST_VAR, AT_LEAST_WHEN, EQUALS_WHEN, VAR_ABOVE, ACTOR_DONE,
		// motions
		HELIX,
		// placements
		CIRCLE_DROP, GLINT, AT_PARENT, TABLE_POINT, RANDOM_TARGET_BONE, RANDOM_TARGET_POINT, ACTION_TARGETS,
		TARGET_ANCHOR, ACTION_TARGET, RANDOM_AROUND, RISING_CIRCLE, SPINNING_RING, WHIRL_LEAF, COLLAPSE_SPARKS, ORBIT_SPAWN, GROWTH_SPAWN, RIBBON_START, EMBER_RING, SPARK_NEAR,
		FLAMES_ON_TARGETS, FLAME_EMBERS, FLAME_SPARKS,
		REVIVE_RISING, REVIVE_AT, REVIVE_SCATTER, REVIVE_RING, REVIVE_FALL,
		// draws
		SPRITE, GROUND_FLIPBOOK, PROJECTOR_OVERLAY, LAYOUT_ON_SCREEN, LAYOUT_AT_CASTER_BONE, LAYOUT_SCALED, SEQUENCE_SPRITE,
		LAYOUT_AT_ANCHOR, LAYOUT_ON_TARGET, LAYOUT_TURNED, NODE_SEQUENCE_SPRITE, LAYOUT_TABLE, SPINNING_MODEL, SEQUENCE_AT_FEET, LAYOUT_SCALED_ON_TARGET,
		TUMBLING_MODEL, LAYOUT_ENGINE_AT_ANCHOR, LAYOUT_ON_POINT, SWAY_OVERLAY, RIPPLE_SILHOUETTE, SPARK_SPRITE,
		BARRIER_WALL, ORBIT_MODEL, GROWTH_MODEL, SEQUENCE_AT_ANCHOR, PULSE_MODEL, LAYOUT_TABLE_AT_SPAWN, LIGHT_RAYS, RIBBON, MOTE_SPRITE,
		FLAME, EMBER, FIRE_SPARK, SCREEN_QUAD, POINT_LAYER, GROUND_LAYER,
		PRIM_MODEL, PRIM_MODEL_AS, SPRITE_TURNED, GROUND_FLIPBOOK_COLOUR, SCREEN_TEX_QUAD, REVIVE_SPARKLE, REVIVE_SPARKLE_SIZED,
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
		{ "sequence_sprite", SEQUENCE_SPRITE }, { "heal_first_target", HEAL_FIRST_TARGET }, { "target_anchor", TARGET_ANCHOR },
		{ "layout_at_anchor", LAYOUT_AT_ANCHOR }, { "anchor_at_bone", ANCHOR_AT_BONE }, { "sound_3d_at", SOUND_3D_AT },
		{ "heal_action_at", HEAL_ACTION_AT }, { "unmark_target", UNMARK_TARGET }, { "tick_above", TICK_ABOVE },
		{ "action_target", ACTION_TARGET }, { "layout_on_target", LAYOUT_ON_TARGET }, { "anchor_at_position", ANCHOR_AT_POSITION },
		{ "layout_turned", LAYOUT_TURNED }, { "heal_action", HEAL_ACTION }, { "screen_fade_at", SCREEN_FADE_AT },
		{ "blink_target", BLINK_TARGET }, { "screen_flash_curve", SCREEN_FLASH_CURVE }, { "screen_flash_off", SCREEN_FLASH_OFF },
		{ "tick_at_node_end", TICK_AT_NODE_END }, { "random_around", RANDOM_AROUND }, { "rising_circle", RISING_CIRCLE },
		{ "node_sequence_sprite", NODE_SEQUENCE_SPRITE }, { "spin", SPIN }, { "spinning_ring", SPINNING_RING },
		{ "layout_table", LAYOUT_TABLE }, { "spinning_model", SPINNING_MODEL }, { "sequence_at_feet", SEQUENCE_AT_FEET },
		{ "whirl_leaf_move", WHIRL_LEAF_MOVE }, { "leaf_gone", LEAF_GONE }, { "whirl_leaf", WHIRL_LEAF },
		{ "layout_scaled_on_target", LAYOUT_SCALED_ON_TARGET }, { "tumbling_model", TUMBLING_MODEL },
		{ "flash_level_raise", FLASH_LEVEL_RAISE }, { "follow_bone", FOLLOW_BONE }, { "sound_3d_at_position", SOUND_3D_AT_POSITION },
		{ "flash_level_clear", FLASH_LEVEL_CLEAR }, { "screen_flash_level", SCREEN_FLASH_LEVEL },
		{ "layout_engine_at_anchor", LAYOUT_ENGINE_AT_ANCHOR }, { "point_at_position", POINT_AT_POSITION },
		{ "layout_on_point", LAYOUT_ON_POINT }, { "mark_ring_from", MARK_RING_FROM }, { "unmark_ring", UNMARK_RING },
		{ "sway_overlay", SWAY_OVERLAY }, { "flash_level_hold", FLASH_LEVEL_HOLD }, { "flash_level_set", FLASH_LEVEL_SET },
		{ "mark_target", MARK_TARGET }, { "tint_target", TINT_TARGET }, { "spark_step", SPARK_STEP }, { "spark_move", SPARK_MOVE },
		{ "spark_gone", SPARK_GONE }, { "collapse_sparks", COLLAPSE_SPARKS }, { "ripple_silhouette", RIPPLE_SILHOUETTE },
		{ "spark_sprite", SPARK_SPRITE }, { "barrier_frame", BARRIER_FRAME }, { "barrier_center", BARRIER_CENTER },
		{ "dead_beams", DEAD_BEAMS }, { "orbit_move", ORBIT_MOVE }, { "growth_step", GROWTH_STEP }, { "orbit_spawn", ORBIT_SPAWN },
		{ "growth_spawn", GROWTH_SPAWN }, { "barrier_wall", BARRIER_WALL }, { "orbit_model", ORBIT_MODEL }, { "growth_model", GROWTH_MODEL },
		{ "spawn_to_feet", SPAWN_TO_FEET }, { "ray_spawn", RAY_SPAWN }, { "mote_step", MOTE_STEP }, { "rays_done", RAYS_DONE },
		{ "ribbon_done", RIBBON_DONE }, { "mote_done", MOTE_DONE }, { "ribbon_start", RIBBON_START }, { "ember_ring", EMBER_RING },
		{ "spark_near", SPARK_NEAR }, { "sequence_at_anchor", SEQUENCE_AT_ANCHOR }, { "pulse_model", PULSE_MODEL },
		{ "layout_table_at_spawn", LAYOUT_TABLE_AT_SPAWN }, { "light_rays", LIGHT_RAYS }, { "ribbon", RIBBON }, { "mote_sprite", MOTE_SPRITE },
		{ "chain_next", CHAIN_NEXT }, { "release_target", RELEASE_TARGET }, { "heal_action_all_at", HEAL_ACTION_ALL_AT },
		{ "sound_pan_at", SOUND_PAN_AT }, { "ember_rise", EMBER_RISE }, { "fire_spark_move", FIRE_SPARK_MOVE }, { "claim_target", CLAIM_TARGET },
		{ "life_out", LIFE_OUT }, { "flames_on_targets", FLAMES_ON_TARGETS }, { "flame_embers", FLAME_EMBERS }, { "flame_sparks", FLAME_SPARKS },
		{ "flame", FLAME }, { "ember", EMBER }, { "fire_spark", FIRE_SPARK },
		{ "spawn_size_word", SPAWN_SIZE_WORD }, { "sound_3d_at_spawn", SOUND_3D_AT_SPAWN }, { "screen_quad", SCREEN_QUAD },
		{ "point_layer", POINT_LAYER }, { "ground_layer", GROUND_LAYER },
		{ "add", ADD }, { "set", SET }, { "copy", COPY }, { "flags", FLAGS }, { "set_when", SET_WHEN }, { "add_when", ADD_WHEN },
		{ "add_below", ADD_BELOW }, { "add_var", ADD_VAR }, { "spin_var", SPIN_VAR }, { "circle_place", CIRCLE_PLACE },
		{ "circle_place_var", CIRCLE_PLACE_VAR }, { "anchor_xz", ANCHOR_XZ }, { "anchor_top", ANCHOR_TOP }, { "rand_mask", RAND_MASK },
		{ "rand_hop", RAND_HOP }, { "index_times", INDEX_TIMES }, { "tick_times", TICK_TIMES }, { "turned_offset", TURNED_OFFSET },
		{ "fade_pulse", FADE_PULSE }, { "grey_pulse", GREY_PULSE }, { "morph", MORPH }, { "spawn_when", SPAWN_WHEN },
		{ "spawn_unless_target_bits", SPAWN_UNLESS_TARGET_BITS }, { "screen_fade_when", SCREEN_FADE_WHEN }, { "wrap", WRAP },
		{ "at_most", VAR_AT_MOST }, { "at_least", VAR_AT_LEAST }, { "equals", VAR_EQUALS }, { "never", NEVER }, { "at_least_var", AT_LEAST_VAR },
		{ "at_least_when", AT_LEAST_WHEN }, { "equals_when", EQUALS_WHEN },
		{ "prim_model", PRIM_MODEL }, { "prim_model_as", PRIM_MODEL_AS }, { "sprite_turned", SPRITE_TURNED },
		{ "ground_flipbook_colour", GROUND_FLIPBOOK_COLOUR }, { "screen_tex_quad", SCREEN_TEX_QUAD },
		{ "revive_ring_step", REVIVE_RING_STEP }, { "above", VAR_ABOVE }, { "revive_rising", REVIVE_RISING }, { "revive_at", REVIVE_AT },
		{ "revive_scatter", REVIVE_SCATTER }, { "revive_ring", REVIVE_RING }, { "revive_fall", REVIVE_FALL },
		{ "revive_sparkle", REVIVE_SPARKLE }, { "revive_sparkle_sized", REVIVE_SPARKLE_SIZED },
		{ "actor_setup", ACTOR_SETUP }, { "actor_step", ACTOR_STEP }, { "actor_done", ACTOR_DONE }, { "stage_clear", STAGE_CLEAR },
		{ "stage_fade", STAGE_FADE }, { "call", CALL },
	};

	inline Program *g_program = nullptr;
	inline int16_t g_anchor[4] = {};              // a task's anchor this tick (anchor_at_bone), when its node keeps none
	inline int16_t g_layer_local[4] = {};         // a task's draws' stack slot (Thunder's lowered layer, then its ground layer's vector)

	// ------------------------------------------------------------------
	// Values
	// ------------------------------------------------------------------
	inline int32_t V(const Val &x) { return x.param ? (x.neg ? -g_program->params[x.v].value : g_program->params[x.v].value) : x.v; }
	inline int32_t G(const Val &x) { return x.param ? (x.neg ? -g_program->params[x.v].game : g_program->params[x.v].game) : x.v; }     // the game's value
	inline uint32_t Mem(const char *name) { auto it = g_program->memory.find(name); return it == g_program->memory.end() ? 0 : it->second; }
	inline bool HasMem(const char *name) { return g_program->memory.count(name) != 0; }
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

	// ------------------------------------------------------------------
	// Node variables (Double's): Fujin/effectprogram.py's tokens, base << 20 | type << 16 | offset;
	// the base is the node, its emitter, the node just spawned (child) or its root
	// ------------------------------------------------------------------
	enum VarType { VAR_I16 = 1, VAR_I32, VAR_U8, VAR_GREY, VAR_U16, VAR_I8 };
	inline TaskNode *g_child = nullptr;           // the node an action or a spawn just made (child.)
	inline int32_t g_spawn_index = 0;             // its number among the tick's spawns of that kind
	inline uint8_t *VarBase(TaskNode *n, int32_t token)
	{
		switch ((token >> 20) & 0xF)
		{
		case 0: return (uint8_t *)n;
		case 1: return (uint8_t *)((FxNode *)n)->emitter;
		case 2: return (uint8_t *)g_child;
		case 3: return (uint8_t *)((FxNode *)n)->root;
		default: return nullptr;
		}
	}
	inline uint8_t *VarAt(TaskNode *n, int32_t token) { uint8_t *b = VarBase(n, token); return b ? b + (token & 0xFFFF) : nullptr; }

	// ------------------------------------------------------------------
	// The act family's actor system (fx_actors.h, Mega Phoenix's copy) on the program's memory: its
	// words (the copy's or its own), the engine's module descriptor with its globals there; the
	// library's functions keep Mega Phoenix's addresses as their dispatch keys
	// ------------------------------------------------------------------
	inline uint32_t g_actor_done = 0;             // the last step's result (1: the system has finished)
	inline uint32_t TaskFunction(int k);
	// a port module's code spawning the original `orig`: the program's task mirroring it, if any (else its port)
	inline uint32_t __cdecl DirectorTask(TaskNode *n);
	inline uint32_t ProgramTaskOf(uint32_t orig)
	{
		if (g_program->director == PORT && orig == g_program->port_root)   // (its root: the director, which makes the module current)
			return g_program->director_fn ? g_program->director_fn : (uint32_t)DirectorTask;
		for (size_t k = 0; k < g_program->tasks.size(); k++)
			if (g_program->tasks[k].code == orig) return TaskFunction((int)k);
		return 0;
	}
	// the original the program's task `fn` mirrors (its "code"), for the port code that reads its node's function
	inline uint32_t ProgramOrigOf(uint32_t fn)
	{
		for (size_t k = 0; k < g_program->tasks.size(); k++)
			if (g_program->tasks[k].code && TaskFunction((int)k) == fn) return g_program->tasks[k].code;
		return 0;
	}
	// the port module of the program (its descriptor with its globals moved, the data words pointing into it
	// its own words), current: its code runs on the program's memory, spawning the program's tasks or thunks of
	// its ports
	inline void SetModuleParams();
	inline Program *g_params_of = nullptr;   // the program whose parameters the port's live ones are (one set: the module's)
	inline void UseModule()
	{
#ifdef FXPROG_ACTORS
		using namespace ff8fx::act;
		Program &g = *g_program;
		if (!g.module) return;
		static bool registered = false;   // (the ports of every module built in: the dispatch of their originals)
		if (!registered)
		{
			registered = true;
#ifdef FF8_FX_LAB
			for (int i = 0; i < ff8fx::fxp::g_lab_module_count; i++) ff8fx::fxp::g_lab_modules[i]();
#endif
		}
		ff8fx::own::active = true;
		ff8fx::own::reloc = g.module_reloc;
		ff8fx::own::task_of = ProgramTaskOf;
		if (g_params_of != &g)
		{
			g_params_of = &g;
			SetModuleParams();
		}
		if (!g.module_ready)
		{
			const Mod *m = find_mod(g.module);
			if (!m) return;   // (not of the act engine: the generic layer only)
			g.module_mod = *m;
			for (uint32_t &w : g.module_mod.g)
				if (w >= g.module_lo && w < g.module_lo + g.module_size) w += g.module_reloc;
			for (size_t k = 0; k < g.module_pointers.size() && k < 8; k++)
			{
				g.module_words[k] = var<uint32_t>(g.module_pointers[k].second) + g.module_reloc;
				g.module_mod.g[g.module_pointers[k].first] = (uint32_t)&g.module_words[k];
			}
			g.module_ready = true;
		}
		g_mod = &g.module_mod;
		g_reloc = g.module_reloc;
		g_own = true;
		g_spawn_hook = ProgramTaskOf;
		g_orig_hook = ProgramOrigOf;
#endif
	}
	inline void UseActors()
	{
#ifdef FXPROG_ACTORS
		using namespace ff8fx::act;
		Program &g = *g_program;
		if (!g.actors_ready)
		{
			actors::register_dispatch();
			g.actor_mem = { Mem("actor_state"), Mem("cam_ptr_a"), Mem("packet_cursor"), Mem("particle_pool"), Mem("particle_next"),
			                Mem("actor_pool"), Mem("actor_next"), Mem("count_a"), Mem("count_b"), g.act_part, g.act_first_part };
			g.actor_mod = actors::MOD_007;
			g.actor_mod.g[G_257F9B0] = Mem("cam_ptr_b");   // the scratch stack's top
			g.actor_mod.g[G_258FB78] = Mem("actor_state");
			g.actor_mod.g[G_258BA90] = 0;                  // (the module's queues: the program spawns its tasks itself)
			g.actor_mod.g[G_258BE30] = 0;
			g.actors_ready = true;
		}
		actors::Use(&g.actor_mem, &g.actor_mod);
#endif
	}
	// the stage's four fade layers (Effect library, 0x1D98992 + k * 0x2C: the level word, the bytes +0x26..+0x28)
	inline void StageClear()
	{
		for (uint32_t p = 0x1D989BA, k = 0; k < 4; k++, p += 0x2C)
		{
			var<uint16_t>(p - 0x28) = 0;
			var<uint8_t>(p) = 0;
			var<uint8_t>(p - 1) = 0;
			var<uint8_t>(p - 2) = 0;
		}
	}
	inline void StageLevel(uint16_t level)
	{
		for (uint32_t p = 0x1D98992, k = 0; k < 4; k++, p += 0x2C) var<uint16_t>(p) = level;
	}
	inline int32_t GetVar(TaskNode *n, int32_t token)
	{
		const uint8_t *p = VarAt(n, token);
		if (!p) return 0;
		switch ((token >> 16) & 0xF)
		{
		case VAR_I16: return *(const int16_t *)p;
		case VAR_I32: return *(const int32_t *)p;
		case VAR_U16: return *(const uint16_t *)p;
		case VAR_I8: return *(const int8_t *)p;
		default: return *p;   // u8, grey: its first byte
		}
	}
	inline void SetVar(TaskNode *n, int32_t token, int32_t v)
	{
		uint8_t *p = VarAt(n, token);
		if (!p) return;
		switch ((token >> 16) & 0xF)
		{
		case VAR_I16: case VAR_U16: *(int16_t *)p = (int16_t)v; break;
		case VAR_I32: *(int32_t *)p = v; break;
		case VAR_GREY: p[0] = p[1] = p[2] = (uint8_t)v; break;
		default: *p = (uint8_t)v; break;
		}
	}
	inline void AddVar(TaskNode *n, int32_t token, int32_t d)
	{
		uint8_t *p = VarAt(n, token);
		if (!p) return;
		if (((token >> 16) & 0xF) == VAR_GREY)
		{
			p[1] = (uint8_t)(p[1] + d);
			p[0] = (uint8_t)(p[0] + d);
			p[2] = (uint8_t)(p[2] + d);
		}
		else SetVar(n, token, GetVar(n, token) + d);
	}
	inline int32_t VarSize(int32_t token)
	{
		switch ((token >> 16) & 0xF)
		{
		case VAR_I16: case VAR_U16: return 2;
		case VAR_I32: case VAR_GREY: return 4;
		default: return 1;
		}
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
	inline void DecodeLayoutB(const Task &t, void *n, uint32_t data) { layouts::DecodeModelPrimLayout(data, Fld<uint8_t>(t, n, F_LAYOUT_B), t.layout_b_size); }
	// a plain node's entity: its entity field, else its slot field's entity
	inline uint8_t *EntityOf(const Task &t, void *n)
	{
		if (t.field[F_ENTITY] >= 0) return *Fld<uint8_t *>(t, n, F_ENTITY);
		return Entity(*Fld<int16_t>(t, n, F_SLOT));
	}
	inline uint32_t *TargetFree() { return (uint32_t *)Mem("target_free"); }   // [slot]: 1 = no director of the effect runs on it (Fire's)
	inline void SpawnChainDirector(int action);
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
		case SPAWN: g_child = (TaskNode *)SpawnTask(V(a[0]), n); break;
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
		case HEAL_FIRST_TARGET: ApplyActionResultToTarget(Ctx()->actions[0].targets); break;   // target 0 of action 0
		case ANCHOR_AT_BONE: // bone: the node's entity's effect point, this tick's anchor
			layouts::GetEffectSpawnPosition(*Fld<uint8_t *>(t, n, F_ENTITY), V(a[0]), 0, g_anchor);
			g_anchor[3] = 0;   // never written by the originals (a stack word), only loaded into the GTE V0 pad
			break;
		case SOUND_3D_AT: // tick, sound, volume: at the node's anchor (or this tick's)
			if (Tick(t, n) == V(a[0]))
				BdPlaySE3D((const void *)fxp::sound((uint32_t)V(a[1]), (uint32_t)G(a[1])), V(a[2]),
				           t.field[F_ANCHOR] >= 0 ? Fld<int16_t>(t, n, F_ANCHOR) : g_anchor);
			break;
		case HEAL_ACTION: ApplyActionResultToTarget(Ctx()->actions[*Fld<int16_t>(t, n, F_ACTION)].targets); break;
		case SCREEN_FADE_AT: if (Tick(t, n) == V(a[0])) ScreenFadeTask(V(a[1]), V(a[2]), V(a[3]), V(a[4])); break;   // tick, the engine's fade's four values
		case SPIN: *Fld<int16_t>(t, n, F_ANGLE) = (int16_t)(*Fld<int16_t>(t, n, F_ANGLE) + *Fld<int16_t>(t, n, F_SPEED)); break;
		case WHIRL_LEAF_MOVE: // climb until, faster from: one tick of the node's leaf (gone: its size at 0 or below)
			layouts::WhirlLeafMove(Fld<layouts::WhirlLeaf>(t, n, F_LEAF), V(a[0]), V(a[1]));
			break;
		case SCREEN_FLASH_CURVE: // rise, level, fall, end: up, held, down (Dispel)
			SetScreenFlash((uint32_t)layouts::ScreenFlashCurve(Tick(t, n), V(a[0]), V(a[1]), V(a[2]), V(a[3])), 0);
			break;
		case SCREEN_FLASH_OFF: SetScreenFlash(0, 0); break;
		case MARK_RING_FROM: // from, bits: from that tick, the bits on every entity of the node's entity's +0x8C ring
			if (Tick(t, n) >= V(a[0])) layouts::MarkRing(*Fld<uint8_t *>(t, n, F_ENTITY), (uint16_t)V(a[1]), true);
			break;
		case UNMARK_RING: layouts::MarkRing(*Fld<uint8_t *>(t, n, F_ENTITY), (uint16_t)V(a[0]), false); break;   // bits
		case FLASH_LEVEL_HOLD: // rise, up, level, fall after, end, down: the program's flash level raised to this tick's (Flare's)
		{
			const int32_t v = layouts::ScreenFlashRiseHoldFall(Tick(t, n), V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]), V(a[5]));
			int32_t &level = var<int32_t>(Mem("flash_level"));
			if (v > level) level = v;
			break;
		}
		case FLASH_LEVEL_SET: if (Tick(t, n) == V(a[0])) var<int32_t>(Mem("flash_level")) = V(a[1]); break;   // tick, level
		case MARK_TARGET: (*Fld<uint16_t *>(t, n, F_ENTITY))[0] |= (uint16_t)V(a[0]); break;   // bits of the entity's flags word, every tick
		case TINT_TARGET: // tint, from, ticks, shift, back from, back ticks, back shift: the entity's colour from the node's saved one
			layouts::TintEntity(*Fld<uint8_t *>(t, n, F_ENTITY), (const void *)V(a[0]), Fld<uint32_t>(t, n, F_COLOUR), Tick(t, n),
			                    V(a[1]), V(a[2]), V(a[3]), V(a[4]), V(a[5]), V(a[6]));
			break;
		case SPARK_STEP: // burst, fade: the spark's size and brightness for this tick (its mode: drawn, not, gone)
		{
			layouts::CollapseSpark *f = Fld<layouts::CollapseSpark>(t, n, F_SPARK);
			f->mode = (int16_t)layouts::CollapseSparkPrepare(f, V(a[0]), V(a[1]));
			break;
		}
		case BARRIER_FRAME: // size shift: the node's barrier turned with its entity, scaled by min(its size << shift, 4096), through the camera
			layouts::BarrierFrame(Fld<layouts::Barrier>(t, n, F_BARRIER), *Fld<uint8_t *>(t, n, F_ENTITY), V(a[0]));
			break;
		case BARRIER_CENTER: // wall, ticks, steps: the barrier's centre climbing the wall model's vertices over its first ticks
			if ((uint32_t)Tick(t, n) < (uint32_t)V(a[1]))
				layouts::BarrierCenter((uint32_t)V(a[0]), Tick(t, n), V(a[2]), V(a[1]), Fld<layouts::Barrier>(t, n, F_BARRIER)->center);
			break;
		case DEAD_BEAMS: // ticks, count, pool: Reflect's dead beams over the first ticks (shared rands while the pool has room)
			if ((uint32_t)Tick(t, n) < (uint32_t)V(a[0]))
			{
				const Pool &pool = g_program->pools[V(a[2])];
				layouts::DeadBeams(pool.base ? MagicBuffer() + pool.storage : pool.storage, pool.size, pool.count, V(a[1]));
			}
			break;
		case ORBIT_MOVE: // the node's orbit turned and tilted a tick
		{
			layouts::Orbit *o = Fld<layouts::Orbit>(t, n, F_ORBIT);
			o->angle = (int16_t)(o->angle + o->dangle);
			o->tilt = (int16_t)(o->tilt + o->dtilt);
			break;
		}
		case GROWTH_STEP: layouts::GrowthStep(Fld<layouts::Growth>(t, n, F_GROWTH), V(a[0])); break;   // least growth
		case SPAWN_TO_FEET: // tick: the node's spawn point's height = its entity's feet (Berserk's, at its start)
			if (Tick(t, n) == V(a[0])) Fld<int16_t>(t, n, F_SPAWN)[1] = *(const int16_t *)(*Fld<uint8_t *>(t, n, F_ENTITY) + 0x24);
			break;
		case RAY_SPAWN: // from, ticks, count, colours, speed, length, its speed, brake, width, its speed, brake: new rays in the node's table
			if ((uint32_t)(Tick(t, n) - V(a[0])) < (uint32_t)V(a[1]))
			{
				const layouts::RayMotion mo = { V(a[4]), V(a[5]), V(a[6]), V(a[7]), V(a[8]), V(a[9]), V(a[10]) };
				layouts::RaySpawn(0x20, Fld<layouts::LightRay>(t, n, F_RAYS), V(a[2]), (const uint32_t *)V(a[3]), mo);
			}
			break;
		case MOTE_STEP: layouts::MoteStep(Fld<layouts::Mote>(t, n, F_MOTE), V(a[0]) != 0, V(a[1])); break;   // rising, frames
		case SPARK_MOVE: // its direction turned, its age
			if (Fld<layouts::CollapseSpark>(t, n, F_SPARK)->mode != -2) layouts::CollapseSparkMove(Fld<layouts::CollapseSpark>(t, n, F_SPARK));
			break;
		case POINT_AT_POSITION: // tick: the node's point = the entity's default effect position, on that tick
			if (Tick(t, n) == V(a[0])) GetDefaultEffectPosition(*Fld<uint8_t *>(t, n, F_ENTITY), Fld<int16_t>(t, n, F_POINT));
			break;
		case FLASH_LEVEL_RAISE: // from, peak, to, up, down: the program's flash level raised to this tick's (Blind: the highest of all its tasks)
		{
			const int32_t v = layouts::ScreenFlashRiseFall(Tick(t, n), V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]));
			int32_t &level = var<int32_t>(Mem("flash_level"));
			if (v >= 0 && v > level) level = v;
			break;
		}
		case FOLLOW_BONE: // bone, until, of (0: the node's entity, 1: the caster): the node's anchor at its effect point while the tick is below `until`, then it stays
			if (Tick(t, n) < V(a[1]))
			{
				int16_t *anchor = Fld<int16_t>(t, n, F_ANCHOR);
				layouts::GetEffectSpawnPosition(V(a[2]) ? Caster() : *Fld<uint8_t *>(t, n, F_ENTITY), V(a[0]), 0, anchor);
				anchor[3] = 0;   // (the original's node word, cleared at its start and never written)
			}
			break;
		case SOUND_3D_AT_POSITION: // tick, sound, volume, of (0: the node's entity, 1: the caster): at its default effect position
			if (Tick(t, n) == V(a[0]))
			{
				int16_t pos[4];
				GetDefaultEffectPosition(V(a[3]) ? Caster() : EntityOf(t, n), pos);
				BdPlaySE3D((const void *)fxp::sound((uint32_t)V(a[1]), (uint32_t)G(a[1])), V(a[2]), pos);
			}
			break;
		case BLINK_TARGET: // from, ticks: the entity's flag bit 3 on the ticks e % (ticks - e) == 0 (e = tick - from)
		{
			uint8_t *e8 = *Fld<uint8_t *>(t, n, F_ENTITY);
			const int32_t e = Tick(t, n) - V(a[0]);
			if ((uint32_t)e < (uint32_t)V(a[1]))
			{
				if (e != 0 && (uint32_t)e % (uint32_t)(V(a[1]) - e) == 0) *e8 |= 8;
				else *(uint16_t *)e8 &= 0xFFF7;
			}
			break;
		}
		case HEAL_ACTION_AT: // tick: target 0 of the node's action takes the result
			if (Tick(t, n) == V(a[0])) ApplyActionResultToTarget(Ctx()->actions[*Fld<int16_t>(t, n, F_ACTION)].targets);
			break;
		case ANCHOR_AT_POSITION: GetDefaultEffectPosition(*Fld<uint8_t *>(t, n, F_ENTITY), g_anchor); break;   // the entity's default effect position
		case UNMARK_TARGET: (*Fld<uint16_t *>(t, n, F_ENTITY))[0] &= (uint16_t)~V(a[0]); break;   // bits of the entity's flags word
		case CHAIN_NEXT: // tick: the next action's director when the node's chain counter is at it (then it counts on)
		{
			int16_t *chain = Fld<int16_t>(t, n, F_CHAIN);
			const int next = *Fld<int16_t>(t, n, F_ACTION) + 1;
			if (*chain == V(a[0]) && next <= Ctx()->actions[0].last_action) SpawnChainDirector(next);
			(*chain)++;
			break;
		}
		case RELEASE_TARGET: TargetFree()[*Fld<int16_t>(t, n, F_SLOT)] = 1; break;   // the node's slot free for the next one
		case HEAL_ACTION_ALL_AT: // tick: every target of the node's action takes the result
			if (Tick(t, n) == V(a[0]))
			{
				const ActionData *ad = &Ctx()->actions[*Fld<int16_t>(t, n, F_ACTION)];
				ApplyActionResultToTargets(ad->targets, ad->target_count);
			}
			break;
		case SOUND_PAN_AT: // tick, sound, volume, pan
			if (Tick(t, n) == V(a[0])) BdPlaySE((const void *)fxp::sound((uint32_t)V(a[1]), (uint32_t)G(a[1])), V(a[2]), V(a[3]));
			break;
		case EMBER_RISE: layouts::EmberRise(Fld<layouts::Ember>(t, n, F_EMBER), V(a[0]), V(a[1])); break;   // speed-up shift, shrink shift
		case ADD: AddVar(n, V(a[0]), V(a[1])); break;   // var, value
		case SET: SetVar(n, V(a[0]), V(a[1])); break;   // var, value
		case COPY: // var, from var, count (of the var's elements)
			if (uint8_t *to = VarAt(n, V(a[0])))
				if (const uint8_t *from = VarAt(n, V(a[1]))) memcpy(to, from, VarSize(V(a[0])) * V(a[2]));
			break;
		case FLAGS: h->flags = (uint16_t)((h->flags & ~V(a[1])) | V(a[0])); break;   // set, clear
		case SET_WHEN: if (GetVar(n, V(a[2])) == V(a[3])) SetVar(n, V(a[0]), V(a[1])); break;   // var, value, test var, test value
		case ADD_WHEN: if (GetVar(n, V(a[2])) == V(a[3])) AddVar(n, V(a[0]), V(a[1])); break;   // var, value, test var, test value
		case ADD_BELOW: if (GetVar(n, V(a[0])) < V(a[2])) AddVar(n, V(a[0]), V(a[1])); break;   // var, value, while below
		case ADD_VAR: AddVar(n, V(a[0]), GetVar(n, V(a[1]))); break;   // var, var added
		case SPIN_VAR: SetVar(n, V(a[0]), (GetVar(n, V(a[0])) + V(a[1])) & V(a[2])); break;   // var, step, mask
		case CIRCLE_PLACE: // centre var, angle var, radius, divisor: the node's position on a circle round its centre
		case CIRCLE_PLACE_VAR: // centre var, angle var, radius var, divisor
		{
			const int32_t radius = s.op == CIRCLE_PLACE ? V(a[2]) : GetVar(n, V(a[2]));
			if (const int16_t *centre = (const int16_t *)VarAt(n, V(a[0])))
				layouts::CirclePlace((int16_t *)(VarBase(n, V(a[0])) + 0x1C), centre, (int16_t)GetVar(n, V(a[1])), radius, V(a[3]));
			break;
		}
		case ANCHOR_XZ: // node's pos var, y added: its position = its emitter's target anchor (x, z; y + this)
			if (uint8_t *node = VarBase(n, V(a[0])))
			{
				parts::CopyAnchorXZFromSource(node, (int16_t *)(node + 0x1C));
				*(int16_t *)(node + 0x1E) = (int16_t)(*(int16_t *)(node + 0x1E) + V(a[1]));
			}
			break;
		case ANCHOR_TOP: if (uint8_t *node = VarBase(n, V(a[0]))) layouts::CopyAnchorTopFromSource(node, (int16_t *)(node + 0x1C)); break;   // node's pos var: its target's top anchor
		case RAND_MASK: SetVar(n, V(a[0]), (CrtRand() & V(a[1])) + V(a[2])); break;   // var, mask, base
		case RAND_HOP: // var, mod, mask: (var + 1 + rand % mod) & mask, in a byte
		{
			const int32_t r = CrtRand() % V(a[1]);
			SetVar(n, V(a[0]), (uint8_t)(r + (uint8_t)GetVar(n, V(a[0])) + 1) & V(a[2]));
			break;
		}
		case INDEX_TIMES: SetVar(n, V(a[0]), g_spawn_index * V(a[1])); break;   // var, step: the spawn's number x step
		case TICK_TIMES: SetVar(n, V(a[0]), (Tick(t, n) * V(a[1])) & V(a[2])); break;   // var, step, mask: the node's tick x step
		case TURNED_OFFSET: // angle var, x mod, x base, y, z: the angle's node moved by (rand % mod + base, y, z) turned by it about y
			if (uint8_t *node = VarBase(n, V(a[0])))
			{
				int16_t v[4];
				const int32_t r = CrtRand() % V(a[1]);
				v[1] = (int16_t)V(a[3]);
				v[2] = (int16_t)V(a[4]);
				v[0] = (int16_t)(r + V(a[2]));
				layouts::TurnedOffset((int16_t *)(node + 0x1C), (int16_t)GetVar(n, V(a[0])), v);
			}
			break;
		case FADE_PULSE: // state, on, fade, colour vars, first, second, first step, second step, grey: a flash over a model
		{
			const layouts::FadePulse pulse = { V(a[4]), V(a[5]), V(a[6]), V(a[7]), V(a[8]) };
			layouts::FadePulseStep((int16_t *)VarAt(n, V(a[0])), (int16_t *)VarAt(n, V(a[1])), (int16_t *)VarAt(n, V(a[2])), VarAt(n, V(a[3])), pulse);
			break;
		}
		case GREY_PULSE: layouts::GreyPulseStep((int16_t *)VarAt(n, V(a[0])), VarAt(n, V(a[1])), V(a[2]), V(a[3]), V(a[4])); break;   // state, colour vars, peak, step, floor
		case MORPH: layouts::MorphVertices((const uint8_t *)V(a[0]), (const uint8_t *)V(a[1]), (uint8_t *)V(a[2]), (int16_t)GetVar(n, V(a[3]))); break;   // vertex sets a, b, model, blend var
		case SPAWN_WHEN: g_child = GetVar(n, V(a[1])) == V(a[2]) ? (TaskNode *)SpawnTask(V(a[0]), n) : nullptr; break;   // task, test var, test value
		case SPAWN_UNLESS_TARGET_BITS: // task, bits: unless the node's action's target record +3 has them
			g_child = (h->ctx->actions[h->action].targets[3] & V(a[1])) ? nullptr : (TaskNode *)SpawnTask(V(a[0]), n);
			break;
		case SCREEN_FADE_WHEN: if (GetVar(n, V(a[0])) == V(a[1])) ScreenFadeTask(V(a[2]), V(a[3]), V(a[4]), V(a[5])); break;   // test var, value, the fade's four values
		case REVIVE_RING_STEP: layouts::ReviveRingStep((uint8_t *)n, V(a[0]), V(a[1])); break;   // spin, rise: a ring sparkle's orbit
#ifdef FXPROG_ACTORS
		case ACTOR_SETUP: UseActors(); ff8fx::act::actors::mf_8CE9A0((uint32_t)n); break;   // the actor system's set-up (its node: data +0x30, state +0x34...)
		case ACTOR_STEP: UseActors(); g_actor_done = ff8fx::act::actors::mf_8CF3D0((uint32_t)n); break;   // a step: update, draws
#endif
		case STAGE_CLEAR: StageClear(); break;
#ifdef FXPROG_ACTORS
		case CALL: UseModule(); ff8fx::act::callp((uint32_t)V(a[0]), (uint32_t)n); break;   // a port module's function, on the node
#endif
		case STAGE_FADE: // level var, step, limit: the level by the step; at the limit, done (and the next phase); the layers at it
		{
			const int32_t step = V(a[1]), limit = V(a[2]);
			AddVar(n, V(a[0]), step);
			const int32_t level = GetVar(n, V(a[0]));
			if (step >= 0 ? level >= limit : level <= limit)
			{
				*(uint8_t *)&h->flags |= 1;
				SetVar(n, V(a[0]), limit);
				h->phase++;
			}
			StageLevel((uint16_t)GetVar(n, V(a[0])));
			break;
		}
		case WRAP: // var, last var: var + 1, back to 0 past the last
			SetVar(n, V(a[0]), GetVar(n, V(a[0])) + 1);
			if (GetVar(n, V(a[0])) > GetVar(n, V(a[1]))) SetVar(n, V(a[0]), 0);
			break;
		case SPAWN_SIZE_WORD: // tick, base, shift: the spawn point's 4th word = (base - the entity's size) >> shift (Thunder's camera offset)
			if (Tick(t, n) == V(a[0])) Fld<int16_t>(t, n, F_SPAWN)[3] = (int16_t)((V(a[1]) - (int32_t)*(const int16_t *)(EntityOf(t, n) + 0x26)) >> V(a[2]));
			break;
		case SOUND_3D_AT_SPAWN: // tick, sound, volume: at the node's spawn point
			if (Tick(t, n) == V(a[0])) BdPlaySE3D((const void *)fxp::sound((uint32_t)V(a[1]), (uint32_t)G(a[1])), V(a[2]), Fld<int16_t>(t, n, F_SPAWN));
			break;
		case FIRE_SPARK_MOVE: layouts::FireSparkMove(Fld<layouts::FireSpark>(t, n, F_FIRE_SPARK), Fld<int16_t>(t, n, F_LIFE), V(a[0]), V(a[1])); break;   // drag shift, shrink
		default: break;
		}
	}

	// a task's hold (after its every-tick actions): true stops its tick there
	inline bool Hold(const Task &t, const Step &s, TaskNode *n)
	{
		switch (s.op)
		{
		case CLAIM_TARGET: // at its first tick, wait until the node's slot is free, then take it (Fire's lone target)
		{
			const int16_t slot = *Fld<int16_t>(t, n, F_SLOT);
			if (TargetFree()[slot] == 0 && Tick(t, n) == 0) return true;
			if (Tick(t, n) == 0) TargetFree()[slot] = 0;
			return false;
		}
		default: return false;
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
		case VAR_AT_MOST: return GetVar(n, V(s.a[0])) <= V(s.a[1]);   // var, value
		case VAR_AT_LEAST: return GetVar(n, V(s.a[0])) >= V(s.a[1]);
		case VAR_EQUALS: return GetVar(n, V(s.a[0])) == V(s.a[1]);
		case NEVER: return false;
		case AT_LEAST_VAR: return GetVar(n, V(s.a[0])) >= GetVar(n, V(s.a[1]));   // var, var
		case AT_LEAST_WHEN: return GetVar(n, V(s.a[2])) == V(s.a[3]) && GetVar(n, V(s.a[0])) >= V(s.a[1]);   // var, value, test var, test value
		case EQUALS_WHEN: return GetVar(n, V(s.a[2])) == V(s.a[3]) && GetVar(n, V(s.a[0])) == V(s.a[1]);
		case VAR_ABOVE: return GetVar(n, V(s.a[0])) > V(s.a[1]);   // var, value
		case ACTOR_DONE: return g_actor_done != 0;
		default: return true;
		}
	}

	// a plain node's placement (`from`: the spawning task, `n` its node; e: the spawn's number in
	// its window, offset: its tick from the window's first)
	inline void PlacePlain(const Spawn &sp, const Task &from, TaskNode *n, uint32_t e, int32_t offset = 0)
	{
		const std::vector<Val> &a = sp.place.a;
		const Task &t = g_program->tasks[sp.task];
		if (sp.place.op == EMBER_RING)
		{
			// count, sequence, scale, angle step, distance base, mask, lift shift, accel base, mask (Berserk's
			// embers): around the spawner's spawn point from one rand angle (each: its distance's rand, then,
			// when the pool has room, its lift's and acceleration's)
			const int16_t *spawn = Fld<int16_t>(from, n, F_SPAWN);
			int32_t angle = CrtRand();
			for (int32_t k = V(a[0]); k > 0; k--)
			{
				const int32_t dist = (CrtRand() & V(a[5])) + V(a[4]);
				TaskNode *f = (TaskNode *)SpawnTask(sp.task, n);
				if (!f) continue;
				layouts::Mote *p = Fld<layouts::Mote>(t, f, F_MOTE);
				p->seq = (uint32_t)V(a[1]);
				p->scale = (int16_t)V(a[2]);
				p->pos[0] = (int16_t)((mul32(ComputeSin(angle), dist) >> 12) + spawn[0]);
				p->pos[2] = (int16_t)((mul32(parts::ComputeCos(angle), dist) >> 12) + spawn[2]);
				const int32_t r1 = CrtRand();
				p->pos[1] = (int16_t)(spawn[1] - (int16_t)(r1 >> V(a[6])));
				const int32_t r2 = CrtRand();
				angle += V(a[3]);
				p->accel = (int8_t)(uint8_t)(V(a[7]) - (r2 & V(a[8])));
			}
			return;
		}
		if (sp.place.op == FLAMES_ON_TARGETS)
		{
			// all, count, delay mod, step, spread num, max, low, lift base, mod, scale base, mod (Fire's
			// directors): around every target of the node's action (all: 1) or its lone target, `count`
			// flames each
			const layouts::FlameRolls r = { V(a[2]), V(a[3]), V(a[4]), V(a[5]), V(a[6]), { V(a[7]), V(a[8]), -1 }, { V(a[9]), V(a[10]), 1 } };
			const ActionData *ad = &Ctx()->actions[*Fld<int16_t>(from, n, F_ACTION)];
			const int targets = V(a[0]) ? ad->target_count : 1;
			for (int j = 0; j < targets; j++)
			{
				const int slot = V(a[0]) ? ad->targets[j * TARGET_STRIDE] : *Fld<int16_t>(from, n, F_SLOT);
				const int32_t spread = layouts::FlameSpread(EntitySize(slot), r);
				int16_t pos[4];
				GetDefaultEffectPosition(Entity(slot), pos);
				for (int k = 0; k < V(a[1]); k++)
				{
					TaskNode *f = (TaskNode *)SpawnTask(sp.task, n);
					layouts::FlameStart(Fld<layouts::Flame>(t, f, F_FLAME), Fld<int16_t>(t, f, F_DELAY), pos, EntityHeight(slot), spread, k, r);
				}
			}
			return;
		}
		if (sp.place.op == FLAME_EMBERS)
		{
			// count, delay mod, step, spread, above, rise base, mod, scale base, mod: around the spawner's flame
			const layouts::EmberRolls r = { V(a[1]), V(a[2]), { -(V(a[3]) >> 1), V(a[3]), 1 }, { 0, V(a[4]), -1 }, { -(V(a[3]) >> 1), V(a[3]), 1 },
			                                { V(a[5]), V(a[6]), -1 }, { V(a[7]), V(a[8]), 1 } };
			for (int k = 0; k < V(a[0]); k++)
			{
				TaskNode *f = (TaskNode *)SpawnTask(sp.task, n);
				layouts::EmberStart(Fld<layouts::Ember>(t, f, F_EMBER), Fld<int16_t>(t, f, F_DELAY), Fld<layouts::Flame>(from, n, F_FLAME)->pos, k, r);
			}
			return;
		}
		if (sp.place.op == FLAME_SPARKS)
		{
			// count, life base, mod, delay mod, step, spread, above, speed, rise base, mod, scale base, mod: around the spawner's flame
			const int32_t spread = V(a[5]), speed = V(a[7]);
			const layouts::SparkRolls r = { { V(a[1]), V(a[2]), 1 }, V(a[3]), V(a[4]), { -(spread >> 1), spread, 1 }, { 0, V(a[6]), -1 },
			                                { -(spread >> 1), spread, 1 }, { -(speed >> 1), speed, 1 }, { V(a[8]), V(a[9]), -1 },
			                                { -(speed >> 1), speed, 1 }, { V(a[10]), V(a[11]), 1 } };
			for (int k = 0; k < V(a[0]); k++)
			{
				TaskNode *f = (TaskNode *)SpawnTask(sp.task, n);
				layouts::FireSparkStart(Fld<layouts::FireSpark>(t, f, F_FIRE_SPARK), Fld<int16_t>(t, f, F_LIFE), Fld<int16_t>(t, f, F_DELAY),
				                        Fld<layouts::Flame>(from, n, F_FLAME)->pos, k, r);
			}
			return;
		}
		if (sp.place.op == ORBIT_SPAWN)
		{
			// count, tilt, angle step, turn, tilt speed base, mask (Reflect's hexagons): around the spawner's
			// barrier, from one shared rand (its turn's side and tilt speed: two more each; a full pool
			// skips a node, its angle not advanced)
			const layouts::Barrier *parent = Fld<layouts::Barrier>(from, n, F_BARRIER);
			int32_t angle = layouts::SharedRand();
			for (int32_t k = V(a[0]); k > 0; k--)
			{
				TaskNode *f = (TaskNode *)SpawnTask(sp.task, n);
				if (!f) continue;
				layouts::Orbit *o = Fld<layouts::Orbit>(t, f, F_ORBIT);
				o->parent = parent;
				o->tilt = (int16_t)V(a[1]);
				o->angle = (int16_t)angle;
				o->dangle = (int16_t)V(a[3]);
				if (layouts::SharedRand() & 1) o->dangle = (int16_t)-o->dangle;
				o->dtilt = (int16_t)(V(a[4]) - (layouts::SharedRand() & V(a[5])));
				angle += V(a[2]);
			}
			return;
		}
		if (sp.place.op == COLLAPSE_SPARKS)
		{
			// count, collapse window, turn, sprite size, scale base, shift (Flare's): around the spawner's
			// anchor, their radius from its entity's size (CRT rand: each spark's start, then its angles)
			uint8_t *ent = *Fld<uint8_t *>(from, n, F_ENTITY);
			const int32_t scale = layouts::SizeScale(ent, V(a[4]), V(a[5]));
			for (int32_t k = 0; k < V(a[0]); k++)
			{
				TaskNode *f = (TaskNode *)SpawnTask(sp.task, n);
				if (!f) break;   // (the pool is full: the original stops)
				layouts::CollapseSparkStart(Fld<layouts::CollapseSpark>(t, f, F_SPARK), Fld<int16_t>(from, n, F_ANCHOR), Tick(from, n), scale,
				                            V(a[1]), V(a[2]), V(a[3]));
			}
			return;
		}
		if (sp.place.op == SPINNING_RING)
		{
			// count, bone, lift, angle step, radius base / mask, speed base / mask, fade base / mask (Aura's
			// flames): one turn and speed for the tick's nodes (CRT rand: the angle, the speed, its side),
			// then each node at the spawner's entity's feet point (rand: its radius, its fade strength)
			uint8_t *ent = *Fld<uint8_t *>(from, n, F_ENTITY);
			int32_t angle = CrtRand();
			int32_t speed = (CrtRand() & V(a[7])) + V(a[6]);
			if (CrtRand() & 1) speed = -speed;
			for (int32_t k = 0; k < V(a[0]); k++)
			{
				if (TaskNode *f = (TaskNode *)SpawnTask(sp.task, n))
				{
					layouts::FeetPoint(ent, V(a[1]), V(a[2]), Fld<int16_t>(t, f, F_POS));
					const int32_t r = CrtRand() & V(a[5]);
					*Fld<int16_t>(t, f, F_ANGLE) = (int16_t)angle;
					*Fld<int16_t>(t, f, F_SPEED) = (int16_t)speed;
					*Fld<int16_t>(t, f, F_RADIUS) = (int16_t)(r + V(a[4]));
					*Fld<int16_t>(t, f, F_FADE) = (int16_t)((CrtRand() & V(a[9])) + V(a[8]));
				}
				angle += V(a[3]);
			}
			return;
		}
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
		case RIBBON_START: // angle, angle step, wave: a ribbon around the spawner's anchor, its first angle angle + the spawner's tick x step
			layouts::RibbonStart(Fld<layouts::Ribbon>(t, m, F_RIBBON), Fld<int16_t>(from, n, F_ANCHOR), Tick(from, n) * V(a[1]) + V(a[0]), V(a[2]));
			break;
		case SPARK_NEAR: // sequence, scale, mask, offset: at the spawner's anchor + (rand & mask) - offset on each axis
		{
			const int16_t *anchor = Fld<int16_t>(from, n, F_ANCHOR);
			layouts::Mote *p = Fld<layouts::Mote>(t, m, F_MOTE);
			p->seq = (uint32_t)V(a[0]);
			p->scale = (int16_t)V(a[1]);
			for (int k = 0; k < 3; k++) p->pos[k] = (int16_t)((CrtRand() & V(a[2])) + anchor[k] - V(a[3]));
			break;
		}
		case GROWTH_SPAWN: // wall, wall from, grow, size, growth, brake, size shift: above the spawner's barrier at the wall's top this tick (scaled by the barrier's)
		{
			uint8_t *ent = *Fld<uint8_t *>(from, n, F_ENTITY);
			int32_t scale = shl32(*(const int16_t *)(ent + 0x26), V(a[6]));
			if (scale > 0x1000) scale = 0x1000;
			layouts::Growth *g = Fld<layouts::Growth>(t, m, F_GROWTH);
			g->parent = Fld<layouts::Barrier>(from, n, F_BARRIER);
			g->height = (int16_t)(mul32((int16_t)layouts::WallHeight((uint32_t)V(a[0]), Tick(from, n) - V(a[1]), V(a[2])), scale) >> 12);
			g->scale = (int16_t)V(a[3]);
			g->speed = (int16_t)V(a[4]);
			g->accel = (int16_t)V(a[5]);
			break;
		}
		case WHIRL_LEAF: // size, turn, climb speed, reach base, shift: around the spawner's anchor, its reach from its entity's size
		{
			uint8_t *ent = *Fld<uint8_t *>(from, n, F_ENTITY);
			layouts::WhirlLeafStart(Fld<layouts::WhirlLeaf>(t, m, F_LEAF), *Fld<int16_t>(from, n, F_ACTION), Fld<int16_t>(from, n, F_ANCHOR),
			                        layouts::SizeScale(ent, V(a[3]), V(a[4])), Fld<int16_t>(from, n, F_COUNTER), V(a[0]), V(a[1]), V(a[2]));
			break;
		}
		case RANDOM_AROUND: // lift, scale, sequence, frames: around the spawner's anchor, spread by its 4th word
		case RISING_CIRCLE: // lift, scale, sequence, frames, points a turn: on a rising circle around the spawner's anchor
		{
			const int16_t *centre = Fld<int16_t>(from, n, F_ANCHOR);
			if (sp.place.op == RANDOM_AROUND) layouts::RandomAround(centre, centre[3], V(a[0]), Fld<int16_t>(t, m, F_POS));
			else layouts::RisingCirclePoint(centre, offset, V(a[4]), V(a[0]), Fld<int16_t>(t, m, F_POS));
			*Fld<int16_t>(t, m, F_SCALE) = (int16_t)V(a[1]);
			*Fld<uint32_t>(t, m, F_SEQ) = fxp::sequence((uint32_t)V(a[2]), (uint32_t)G(a[2]));
			*Fld<int16_t>(t, m, F_END) = (int16_t)V(a[3]);
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

	// a spawn's placement of each new piece around the spawner, then its init actions (on child.)
	inline void PlaceNode(const Spawn &sp, Particle *r);
	inline void Place(const Spawn &sp, Particle *r, const Task &from)
	{
		g_child = nullptr;
		PlaceNode(sp, r);
		for (const Step &s : sp.init) Act(from, s, (TaskNode *)r);
	}
	inline void PlaceNode(const Spawn &sp, Particle *r)
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
			g_child = (TaskNode *)m;
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
		// the revive sparkles (Phoenix Down's, Life's): each spawns its own node, under the spawner
		case REVIVE_RISING: // sequence a, b, last frame, shade, below, steps
		{
			const layouts::ReviveRising rising = { (uint32_t)V(a[0]), (uint32_t)V(a[1]), V(a[2]), V(a[3]), V(a[4]), V(a[5]) };
			g_child = (TaskNode *)layouts::ReviveRisingSpawn((TaskQueue *)g_program->pools[g_program->tasks[sp.task].pool].queue, TaskFunction(sp.task),
			                                                 (uint8_t *)r, rising);
			break;
		}
		case REVIVE_AT: // sequence, last frame, shade: at the anchor
		case REVIVE_SCATTER: // sequence, last frame, shade: scattered above it
		{
			TaskQueue *q = (TaskQueue *)g_program->pools[g_program->tasks[sp.task].pool].queue;
			g_child = (TaskNode *)(sp.place.op == REVIVE_AT ? layouts::ReviveSparkleAt(q, TaskFunction(sp.task), r, (uint32_t)V(a[0]), V(a[1]), V(a[2]))
			                                                : layouts::ReviveScatterSpawn(q, TaskFunction(sp.task), (uint8_t *)r, (uint32_t)V(a[0]), V(a[1]), V(a[2])));
			break;
		}
		case REVIVE_RING: // sequence, last frame, divisor sub, div, add: on the ring
			g_child = (TaskNode *)layouts::ReviveRingSpawn((TaskQueue *)g_program->pools[g_program->tasks[sp.task].pool].queue, TaskFunction(sp.task),
			                                               (uint8_t *)r, (uint32_t)V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]));
			break;
		case REVIVE_FALL: // sequence, last frame, circle divisor, lift base, mask, speed base, mask: falling
			g_child = (TaskNode *)layouts::ReviveFallSpawn((TaskQueue *)g_program->pools[g_program->tasks[sp.task].pool].queue, TaskFunction(sp.task),
			                                               (uint8_t *)r, (uint32_t)V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]), V(a[5]), V(a[6]));
			break;
		default: g_child = (TaskNode *)SpawnTask(sp.task, r); break;   // at_parent: the new node takes the spawner's place
		}
	}

	inline void DrawOne(const Draw &d, Particle *p)
	{
		const std::vector<Val> &a = d.draw.a;
		const bool hidden = (p->h.flags & 4) != 0;
		TaskNode *n = (TaskNode *)p;
		auto word = [&](const Val &v) { const uint8_t *q = VarAt(n, V(v)); return q ? *(const uint32_t *)q : 0u; };
		switch (d.draw.op)
		{
		case PRIM_MODEL: // model, angle, scale, colour, fade vars: the node's prim model at its position
		case PRIM_MODEL_AS: // model (data), angle, scale, colour, fade vars
			layouts::EffectModelDraw(p->h.pos, hidden, (const int16_t *)VarAt(n, V(a[1])), (const int32_t *)VarAt(n, V(a[2])), word(a[3]),
			                         GetVar(n, V(a[4])), d.draw.op == PRIM_MODEL ? word(a[0]) : (uint32_t)V(a[0]), PacketCursor());
			break;
		case SPRITE_TURNED: // sequence, frame, x angle, y angle, scale, colour vars: a flipbook frame turned by its angles
			layouts::EffectSpriteTurned(p->h.pos, hidden, (int16_t)GetVar(n, V(a[2])), (int16_t)GetVar(n, V(a[3])), (const int32_t *)VarAt(n, V(a[4])),
			                            word(a[0]), (int16_t)GetVar(n, V(a[1])), word(a[5]), PacketCursor());
			break;
		case GROUND_FLIPBOOK_COLOUR: // sequence, tilt, height, frame, colour var: a flipbook frame on the ground under the node
			parts::DrawGroundFlipbook(p->h.pos, hidden, fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), (int16_t)V(a[1]), (int16_t)V(a[2]),
			                          (int16_t)V(a[3]), word(a[4]), PacketCursor());
			break;
		case REVIVE_SPARKLE: layouts::ReviveSparkleDraw((const uint8_t *)n, (uint16_t)GetVar(n, V(a[0])), PacketCursor()); break;   // size var: a revive sparkle
		case REVIVE_SPARKLE_SIZED: layouts::ReviveSparkleDraw((const uint8_t *)n, (uint16_t)V(a[0]), PacketCursor()); break;   // size
		case SCREEN_TEX_QUAD: // texture page x, y, CLUT x, y, u, v, width, height: a raw textured quad, its bottom on the node projected
		{
			const layouts::TexQuad q = { V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]), V(a[5]), V(a[6]), V(a[7]) };
			PacketCursor() = layouts::ScreenTexQuad(p->h.pos, q, PacketCursor());
			break;
		}
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
		arg.morph = HasMem("magic_buffer") ? MagicBuffer() + g_program->morph : 0;   // (Reflect: no magic buffer)
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
		case LAYOUT_TABLE: // per-object words, bone, size shift: at the entity's feet scaled by the square root of its size
		{
			layouts::TableArg table;
			layouts::SqrtSizeFrame(*Fld<uint8_t *>(t, n, F_ENTITY), V(a[2]), V(a[1]), &table.m);
			table.flags = (uint32_t)V(a[0]);
			table.morph = arg.morph;
			table.cursor = arg.cursor;
			const int frames = layouts::PlayWithTable(Fld<uint8_t>(t, n, F_LAYOUT), &table);
			left = left < 0 ? frames : left | frames;
			break;
		}
		case LAYOUT_SCALED_ON_TARGET: // layout (0, 1: b), at (0: the anchor's x / z on the feet, 1: the effect position now, 2: the anchor), depth base, shift (-1: base as is), scale base, shift, flags, 16-bit record scale, additive objects a, b (-1: none; their gouraud quads only), far objects a, b (at a quarter depth)
		{
			// Aero's wind: the anchor callback scaled by the entity's size, its depth from it, its
			// matrix the program's camera matrix
			uint8_t *e = *Fld<uint8_t *>(t, n, F_ENTITY);
			layouts::AnchorArg anchor_arg;
			const int16_t *anchor = Fld<int16_t>(t, n, F_ANCHOR);
			if (V(a[1]) == 0)
			{
				anchor_arg.anchor[0] = anchor[0];
				anchor_arg.anchor[2] = anchor[2];
				anchor_arg.anchor[1] = *(const int16_t *)(e + 0x24);
				anchor_arg.anchor[3] = 0;
			}
			else if (V(a[1]) == 2) memcpy(anchor_arg.anchor, anchor, sizeof(anchor_arg.anchor));
			else GetDefaultEffectPosition(e, anchor_arg.anchor);
			const int32_t s = layouts::SizeScale(e, V(a[4]), V(a[5]));
			anchor_arg.scale[0] = anchor_arg.scale[1] = anchor_arg.scale[2] = s;
			anchor_arg.scaled = 1;
			anchor_arg.depth = V(a[3]) < 0 ? V(a[2]) : layouts::DepthFromSize(e, V(a[2]), V(a[3]));
			anchor_arg.morph = arg.morph;
			anchor_arg.honoured = (uint32_t)V(a[6]);
			anchor_arg.cursor = arg.cursor;
			anchor_arg.matrix = g_program->camera_matrix ? &var<Mat4x3>(Mem("camera_matrix")) : &Camera();
			anchor_arg.short_scale = V(a[7]) != 0;
			for (int k = 8; k < 10; k++)   // (Zombie's mist)
				if ((uint32_t)V(a[k]) < 32) anchor_arg.additive_objects |= 1u << V(a[k]);
			anchor_arg.quads_gouraud_only = true;
			for (int k = 10; k < 12; k++)   // (Flare's burst and ring)
				if ((uint32_t)V(a[k]) < 32) anchor_arg.far_objects |= 1u << V(a[k]);
			const int frames = layouts::PlayAtAnchor(Fld<uint8_t>(t, n, V(a[0]) ? F_LAYOUT_B : F_LAYOUT), &anchor_arg);
			left = left < 0 ? frames : left | frames;
			break;
		}
		case LAYOUT_ENGINE_AT_ANCHOR: // record flags honoured, depth shift, additive objects a, b (-1: none): at the node's anchor, the engine's renderer
		{
			// Blind's: each object's offset + the anchor through the camera, drawn by 0x572200 (its depth
			// not written) or, for the additive objects, as their textured quads only, additive
			layouts::AnchorArg anchor_arg;
			memcpy(anchor_arg.anchor, Fld<int16_t>(t, n, F_ANCHOR), sizeof(anchor_arg.anchor));
			anchor_arg.morph = arg.morph;
			anchor_arg.honoured = (uint32_t)V(a[0]);
			anchor_arg.cursor = arg.cursor;
			anchor_arg.engine_draw = true;
			anchor_arg.ot_shift = V(a[1]);
			for (int k = 2; k < 4; k++)
				if ((uint32_t)V(a[k]) < 32) anchor_arg.additive_objects |= 1u << V(a[k]);
			const int frames = layouts::PlayAtAnchor(Fld<uint8_t>(t, n, F_LAYOUT), &anchor_arg);
			left = left < 0 ? frames : left | frames;
			break;
		}
		case LAYOUT_ON_POINT: // layout (0, 1: b), at (0: the anchor, 1: the point), of (0: the node's entity, 1: the caster), ahead (-1: none), depth base, shift, record flags
		{
			// Petrify Stare's: the anchor callback at a node point (moved ahead of the entity's facing by
			// the unit circle >> `ahead`), its depth from that entity's size
			uint8_t *e = V(a[2]) ? Caster() : *Fld<uint8_t *>(t, n, F_ENTITY);
			const int16_t *point = Fld<int16_t>(t, n, V(a[1]) ? F_POINT : F_ANCHOR);
			layouts::AnchorArg anchor_arg;
			if (V(a[3]) >= 0) layouts::AheadOfFacing(e, point, V(a[3]), anchor_arg.anchor);
			else memcpy(anchor_arg.anchor, point, 6);
			anchor_arg.anchor[3] = 0;   // (a word the originals never write: only loaded into the GTE V0 pad)
			anchor_arg.depth = layouts::DepthFromSize(e, V(a[4]), V(a[5]));
			anchor_arg.morph = arg.morph;
			anchor_arg.honoured = (uint32_t)V(a[6]);
			anchor_arg.cursor = arg.cursor;
			const int frames = layouts::PlayAtAnchor(Fld<uint8_t>(t, n, V(a[0]) ? F_LAYOUT_B : F_LAYOUT), &anchor_arg);
			left = left < 0 ? frames : left | frames;
			break;
		}
		case SWAY_OVERLAY: // from, ticks, wave, reach base, shift, lift shift, amp base, step, phase step, cast flags that skip it
		{
			// Zombie's: the node's entity redrawn lifted and swayed by the s16 [4096] wave table, flat
			// additive from black to its tint, over from .. from + ticks - 1
			const int32_t e = Tick(t, n) - V(a[0]);
			if ((uint32_t)e >= (uint32_t)V(a[1]) || (Ctx()->flags & (uint32_t)V(a[9]))) break;
			uint8_t *ent = *Fld<uint8_t *>(t, n, F_ENTITY);
			layouts::SwayArg o;
			layouts::SwayOverlayParams(e, V(a[1]), layouts::SizeScale(ent, V(a[3]), V(a[4])), V(a[5]), V(a[6]), V(a[7]), V(a[8]), &o);
			layouts::DrawSwayOverlay(ent, &o, (const int16_t *)V(a[2]), PacketCursor());
			break;
		}
		case RIPPLE_SILHOUETTE: // from, ticks, tables (distance, weights, sine, one block): the node's entity redrawn rippled around its anchor
			layouts::RippleSilhouetteTick(*Fld<uint8_t *>(t, n, F_ENTITY), Fld<int16_t>(t, n, F_ANCHOR), Tick(t, n) - V(a[0]), V(a[1]),
			                              Fld<int32_t>(t, n, F_RIPPLE), layouts::RippleTablesAt((uint32_t)V(a[2])));
			break;
		case SEQUENCE_AT_ANCHOR: // sequence, from, rotation a, b: at the node's anchor, frame = the tick - from
			layouts::DrawSequenceSprite(Fld<int16_t>(t, n, F_ANCHOR), fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), (int16_t)(Tick(t, n) - V(a[1])),
			                            V(a[2]), V(a[3]), PacketCursor());
			break;
		case PULSE_MODEL: // model, from, ticks, scale base, fade base, draw mode: at the node's anchor, pulsing and fading
			layouts::PulseModelDraw((uint32_t)V(a[0]), Fld<int16_t>(t, n, F_ANCHOR), Tick(t, n) - V(a[1]), V(a[2]), V(a[3]), V(a[4]), (uint32_t)V(a[5]),
			                        PacketCursor());
			break;
		case LAYOUT_TABLE_AT_SPAWN: // words: the node's layout through the table callback, the camera its frame, at its spawn point
		{
			layouts::TableArg table;
			table.m = Camera();
			memcpy(table.offset, Fld<int16_t>(t, n, F_SPAWN), sizeof(table.offset));
			table.flags = (uint32_t)V(a[0]);
			table.morph = arg.morph;
			table.cursor = arg.cursor;
			const int frames = layouts::PlayWithTable(Fld<uint8_t>(t, n, F_LAYOUT), &table);
			left = left < 0 ? frames : left | frames;
			break;
		}
		case LIGHT_RAYS: // the node's rays drawn around its anchor, then moved (the count drawn: its drawn field)
			*Fld<int32_t>(t, n, F_DRAWN) = layouts::RayDraw(0x20, Fld<layouts::LightRay>(t, n, F_RAYS), Fld<int16_t>(t, n, F_ANCHOR), PacketCursor());
			break;
		case RIBBON: // push ticks, per tick, angle step, fade, strip window, reset window: the node's ribbon a tick
		{
			const layouts::RibbonMotion mo = { V(a[0]), V(a[1]), V(a[2]), V(a[3]) };
			layouts::RibbonTick(Fld<layouts::Ribbon>(t, n, F_RIBBON), Tick(t, n), mo, (const uint8_t *)V(a[4]), (const uint8_t *)V(a[5]), PacketCursor());
			break;
		}
		case MOTE_SPRITE: layouts::MoteDraw(Fld<layouts::Mote>(t, n, F_MOTE), PacketCursor()); break;   // the node's sprite sequence
		case SCREEN_QUAD: PacketCursor() = layouts::ScreenQuad((const void *)V(a[0]), (uint32_t)V(a[1]), PacketCursor()); break;   // colour word, bucket: a flat quad over the whole screen
		case POINT_LAYER: // sequence, from, lift, size: at the node's spawn point lowered by lift, frame = the tick - from, its 4th word the camera offset
			layouts::PointLayer(Fld<int16_t>(t, n, F_SPAWN), V(a[2]), V(a[3]), fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), (int16_t)(Tick(t, n) - V(a[1])),
			                    g_layer_local, PacketCursor());
			break;
		case GROUND_LAYER: // sequence, from, tilt, push: on a plane at the entity's feet under the node's spawn point, frame = the tick - from
			layouts::GroundLayer(Fld<int16_t>(t, n, F_SPAWN), EntityOf(t, n), V(a[2]), V(a[3]), fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])),
			                     (int16_t)(Tick(t, n) - V(a[1])), g_layer_local, PacketCursor());
			break;
		case FLAME: // sequence, glow sequence, shade shift, glow tilt, mode, high, span, base: the node's flame, frame = the tick, over its ground glow
		{
			const layouts::FlameLook look = { fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), fxp::sequence((uint32_t)V(a[1]), (uint32_t)G(a[1])),
			                                  V(a[2]), V(a[3]), V(a[4]), V(a[5]), V(a[6]), V(a[7]) };
			layouts::FlameDraw(Fld<layouts::Flame>(t, n, F_FLAME), (int16_t)Tick(t, n), look, PacketCursor());
			break;
		}
		case EMBER: // sequence, shade shift: the node's ember, frame = the tick
			layouts::EmberDraw(Fld<layouts::Ember>(t, n, F_EMBER), (int16_t)Tick(t, n), fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), V(a[1]), PacketCursor());
			break;
		case FIRE_SPARK: // sprite, last frame, header byte +0x20, draw mode, shade shift: the node's spark, frame = last - its life
		{
			const layouts::SparkLook look = { V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]) };
			layouts::FireSparkDraw(Fld<layouts::FireSpark>(t, n, F_FIRE_SPARK), *Fld<int16_t>(t, n, F_LIFE), look, PacketCursor());
			break;
		}
		case BARRIER_WALL: // wall, from, ticks, grow, fade: the wall through the node's barrier, growing, its texture scrolling, then fading
		{
			const int32_t e = Tick(t, n) - V(a[1]);
			if ((uint32_t)e >= (uint32_t)V(a[2])) break;
			layouts::WallDraw((uint32_t)V(a[0]), Tick(t, n), layouts::WallHeight((uint32_t)V(a[0]), e, V(a[3])), layouts::WallFade(e, V(a[3]), V(a[4])),
			                  &Fld<layouts::Barrier>(t, n, F_BARRIER)->view, PacketCursor());
			break;
		}
		case ORBIT_MODEL: // model, fade from, fade ticks, draw mode, sin / cos table: the node's orbit around its barrier's centre
			layouts::OrbitDraw((uint32_t)V(a[0]), Fld<layouts::Orbit>(t, n, F_ORBIT), Tick(t, n), V(a[1]), V(a[2]), (uint32_t)V(a[3]), (uint32_t)V(a[4]),
			                   PacketCursor());
			break;
		case GROWTH_MODEL: // model, fade ticks, draw mode: the node's ring above its barrier
			layouts::GrowthDraw((uint32_t)V(a[0]), Fld<layouts::Growth>(t, n, F_GROWTH), Tick(t, n), V(a[1]), (uint32_t)V(a[2]), PacketCursor());
			break;
		case SPARK_SPRITE: // sequence: the node's spark, when its mode draws it
		{
			const layouts::CollapseSpark *f = Fld<layouts::CollapseSpark>(t, n, F_SPARK);
			if (f->mode >= 0) layouts::CollapseSparkDraw(f, f->mode, fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), PacketCursor());
			break;
		}
		case TUMBLING_MODEL: // model, draw mode: the node's leaf (not when it is gone)
		{
			const layouts::WhirlLeaf *f = Fld<layouts::WhirlLeaf>(t, n, F_LEAF);
			if (f->scale > 0) layouts::DrawTumblingModel((uint32_t)V(a[0]), f->ang, f->scale, f->pos, (uint32_t)V(a[1]), PacketCursor());
			break;
		}
		case SPINNING_MODEL: // model, fade in, from, out, draw mode, nearer: the node's, turned by its angle, scaled by its radius
			layouts::DrawSpinningModel((uint32_t)V(a[0]), Fld<int16_t>(t, n, F_POS), *Fld<int16_t>(t, n, F_ANGLE), *Fld<int16_t>(t, n, F_RADIUS),
			                           layouts::FadeInOut(Tick(t, n), *Fld<int16_t>(t, n, F_FADE), V(a[1]), V(a[2]), V(a[3])),
			                           (uint32_t)(uint16_t)V(a[4]), V(a[5]), PacketCursor());
			break;
		case SEQUENCE_AT_FEET: // sequence, from, frames, bone, lift, rotation a, b: frame = tick - from
		{
			const int32_t e = Tick(t, n) - V(a[1]);
			if ((uint32_t)e >= (uint32_t)V(a[2])) break;
			int16_t pos[4];
			layouts::FeetPoint(*Fld<uint8_t *>(t, n, F_ENTITY), V(a[3]), V(a[4]), pos);
			layouts::DrawSequenceSprite(pos, fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])), (int16_t)e, V(a[5]), V(a[6]), PacketCursor());
			break;
		}
		case NODE_SEQUENCE_SPRITE: // rotation b: the node's sequence, frame = the counter, at its position, rotation a = its scale
			layouts::DrawSequenceSprite(Fld<int16_t>(t, n, F_POS), *Fld<uint32_t>(t, n, F_SEQ), (int16_t)Tick(t, n),
			                            *Fld<int16_t>(t, n, F_SCALE), V(a[0]), PacketCursor());
			break;
		case SEQUENCE_SPRITE: // sequence, rotation a, b: frame = the counter, at the node's position
			layouts::DrawSequenceSprite(Fld<int16_t>(t, n, F_POS), fxp::sequence((uint32_t)V(a[0]), (uint32_t)G(a[0])),
			                            (int16_t)Tick(t, n), V(a[1]), V(a[2]), PacketCursor());
			break;
		case LAYOUT_AT_ANCHOR: // prim depth, record flags honoured: each object's offset + the node's anchor through the camera
		{
			layouts::AnchorArg anchor_arg;
			memcpy(anchor_arg.anchor, Fld<int16_t>(t, n, F_ANCHOR), sizeof(anchor_arg.anchor));
			anchor_arg.depth = V(a[0]);
			anchor_arg.morph = arg.morph;
			anchor_arg.honoured = (uint32_t)V(a[1]);
			anchor_arg.cursor = arg.cursor;
			anchor_arg.matrix = g_program->camera_matrix ? &var<Mat4x3>(Mem("camera_matrix")) : &Camera();
			left = layouts::PlayAtAnchor(Fld<uint8_t>(t, n, F_LAYOUT), &anchor_arg);
			break;
		}
		case LAYOUT_TURNED: // layout (0, 1: layout_b), bone, y, depth, depth point, scale base, shift, record flags, scaled, engine draw
		{
			// in a frame of the node's entity: turned with it, at its effect point `bone` (-1: the node's
			// anchor) - y: that point's (0), its feet (1: +0x24) or the node's spawn point lowered by the
			// size (2: s / 16 + s / 4) - scaled by its size (scaled 1; 0: not; -1: when the camera
			// matrix's m[1][0] is not 0, Slow's vanilla read); depth: the point's depth in the frame, or
			// as given; engine draw: 0x572200, the depth not written (Haste, Slow)
			uint8_t *e = *Fld<uint8_t *>(t, n, F_ENTITY);
			layouts::FrameArg frame;
			const int32_t s = layouts::SizeScale(e, V(a[5]), V(a[6]));
			frame.scale[0] = frame.scale[1] = frame.scale[2] = s;
			frame.scaled = V(a[8]) >= 0 ? V(a[8]) : var<Mat4x3>(Mem("camera_matrix")).m[1][0];
			frame.honoured = (uint32_t)V(a[7]);
			frame.cursor = arg.cursor;
			frame.morph = arg.morph;
			frame.matrix = g_program->camera_matrix ? &var<Mat4x3>(Mem("camera_matrix")) : &Camera();
			frame.engine_draw = V(a[9]) != 0;
			int16_t sp[4];
			if (V(a[1]) >= 0) layouts::GetEffectSpawnPosition(e, V(a[1]), 0, sp);
			else memcpy(sp, Fld<int16_t>(t, n, F_ANCHOR), sizeof(sp));
			int32_t point[3] = { sp[0], sp[1], sp[2] };
			if (V(a[2]) == 1) point[1] = *(const int16_t *)(e + 0x24);
			if (V(a[2]) == 2) point[1] = (int32_t)Fld<int16_t>(t, n, F_SPAWN)[1] - (s >> 4) - (s >> 2);
			layouts::TargetFrame(e, point, &frame.m);
			frame.depth = V(a[4]) ? layouts::PointDepth(&frame.m, e, (const int16_t *)V(a[4])) : V(a[3]);
			if (V(a[4])) GteSetTransVector(&frame.m);
			const int frames = layouts::PlayInFrame(Fld<uint8_t>(t, n, V(a[0]) ? F_LAYOUT_B : F_LAYOUT), &frame);
			left = left < 0 ? frames : left | frames;   // a task's layouts all finished: its layout_end
			break;
		}
		case LAYOUT_ON_TARGET: // depth base, shift, record flags honoured, nearer object, by: at this tick's anchor
		{
			layouts::AnchorArg anchor_arg;
			memcpy(anchor_arg.anchor, g_anchor, sizeof(anchor_arg.anchor));
			anchor_arg.depth = layouts::DepthFromSize(*Fld<uint8_t *>(t, n, F_ENTITY), V(a[0]), V(a[1]));
			anchor_arg.morph = arg.morph;
			anchor_arg.honoured = (uint32_t)V(a[2]);
			anchor_arg.cursor = arg.cursor;
			anchor_arg.nearer_object = V(a[3]);
			anchor_arg.nearer_by = V(a[4]);
			left = layouts::PlayAtAnchor(Fld<uint8_t>(t, n, F_LAYOUT), &anchor_arg);
			break;
		}
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
		int left = -1;                            // the frames left of the layouts drawn this tick (-1: none drawn)
		auto draws = [&]()
		{
			memset(g_layer_local, 0, sizeof(g_layer_local));
			for (const Draw &d : t.draws)
			{
				if (!t.plain && d.gate && !(h->flags & d.gate)) continue;
				if (d.limit == BELOW && !(Tick(t, n) < V(d.value))) continue;
				if (d.limit == AT_MOST && !((uint16_t)Tick(t, n) <= (uint16_t)V(d.value))) continue;
				if (d.limit == AT_LEAST && !(Tick(t, n) >= V(d.value))) continue;
				if (d.limit == WITHIN && !((uint32_t)(Tick(t, n) - V(d.value)) < (uint32_t)V(d.count))) continue;
				if (d.when.op && !Holds(d.when, n)) continue;
				FX_PART(d.tag);
				if (t.plain) DrawPlain(d, t, n, left);
				else DrawOne(d, p);
			}
			if (!t.draws.empty()) FX_PART(0);   // what a task does after its draws is no part's
		};
		if (t.native) // the port's task function, its module current
		{
			UseModule();
			void *body = nullptr;
#ifdef FXPROG_ACTORS
			body = ff8fx::act::port_of(t.native);
#endif
			if (!body) body = ff8fx::own::find(t.native);
			return body ? ((uint32_t (__cdecl *)(TaskNode *))body)(n) : TASK_END;
		}
		if (t.draw_only == DRAW_ONLY_SKIP && DrawOnly()) return 0;
		if (int16_t *delay = Fld<int16_t>(t, n, F_DELAY); delay && *delay > 0)   // (a plain node's delay: a tick of its own, not while only drawing)
		{
			if (!DrawOnly()) (*delay)--;
			return 0;
		}
		for (const Step &s : t.every_tick) Act(t, s, n);
		if (t.hold.op && Hold(t, t.hold, n)) return 0;
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
		for (const Step &s : t.moves) Act(t, s, n);
		if (t.draws_first) draws();
		if (t.draw_only == DRAW_ONLY_DRAWS && DrawOnly()) return 0;
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
					if ((h->flags & sp.gate) && w.has(h->counter)) Place(sp, p, t);
				}
			}
		}
		for (const Spawn &sp : t.spawns)
		{
			if (!t.plain && sp.gate && !(h->flags & sp.gate)) continue;
			const int16_t c = (int16_t)Tick(t, n);
			const fxp::Window w = { (int16_t)V(sp.first), (int16_t)V(sp.last) };
			if (!w.has(c)) continue;
			const bool plain = sp.task >= 0 && g_program->tasks[sp.task].plain;   // (a spinning ring: one or more)
			if (sp.every_kind) // one every n ticks from the window's first
			{
				const int32_t every = V(sp.every);
				if (every <= 0 || (c - w.first) % every != 0) continue;
				const uint32_t e = (uint32_t)((c - w.first) / every);
				if (plain) PlacePlain(sp, t, n, e, c - w.first);
				else
				{
					g_spawn_index = 0;
					Place(sp, p, t);
				}
				continue;
			}
			fxp::Schedule schedule;
			for (int j = 0; j < 4; j++)
			{
				schedule.from[j] = (int16_t)V(sp.schedule[2 * j]);
				schedule.count[j] = (int16_t)V(sp.schedule[2 * j + 1]);
			}
			const int32_t count = schedule.at(c);
			for (int32_t m = count; m > 0; m--)
				if (plain) PlacePlain(sp, t, n, 0);
				else
				{
					g_spawn_index = count - m;
					Place(sp, p, t);
				}
		}
		for (const Step &s : t.events) Act(t, s, n);
		if (!t.draws_first) draws();
		for (const Step &s : t.after) Act(t, s, n);
		if (int16_t *c = CounterOf(t, n)) (*c)++;
		if (!t.plain) return EndWhenDone(h);
		bool ends = false;
		switch (t.end.op)
		{
		case TICK_AT_LEAST: ends = Tick(t, n) >= V(t.end.a[0]); break;
		case LAYOUT_END: ends = left == 0; break;   // every layout drawn this tick has finished
		case TICK_ABOVE: ends = Tick(t, n) > V(t.end.a[0]); break;   // the counter (before this tick's step) reached it
		case TICK_AT_NODE_END: ends = Tick(t, n) >= *Fld<int16_t>(t, n, F_END); break;   // its own frame count
		case LEAF_GONE: ends = Fld<layouts::WhirlLeaf>(t, n, F_LEAF)->scale <= 0; break;
		case SPARK_GONE: ends = Fld<layouts::CollapseSpark>(t, n, F_SPARK)->mode == -2; break;
		case RAYS_DONE: ends = Tick(t, n) > V(t.end.a[0]) && *Fld<int32_t>(t, n, F_DRAWN) == 0; break;   // after that tick, once no ray was drawn
		case RIBBON_DONE: ends = Tick(t, n) > V(t.end.a[0]) && Fld<layouts::Ribbon>(t, n, F_RIBBON)->count < 2; break;   // after that tick, fewer than 2 positions
		case MOTE_DONE: ends = (int8_t)Fld<layouts::Mote>(t, n, F_MOTE)->counter >= V(t.end.a[0]); break;   // its frame reached that
		case LIFE_OUT: ends = *Fld<int16_t>(t, n, F_LIFE) < 0; break;   // its life counted down past 0
		default: break;
		}
		if (!ends) return 0;
		for (const Step &s : t.at_end) Act(t, s, n);
		return TASK_END;
	}

	// ------------------------------------------------------------------
	// The per-action director, the setup, the file loader
	// ------------------------------------------------------------------
	static const uint32_t CAM_SNAPSHOT = 0x2793E58;       // Effect_SharedCamMatrixSnapshot

	inline int16_t &ActCountdown(RootNode *r) { return *(int16_t *)((uint8_t *)r + 0x60); }
	// the act family's actor pools (Mega Phoenix 0x8CE650): carved from the arena top, cleared (0x8DCC00), their
	// cursors zeroed; the stage fade in
	inline void ActPools(RootNode *r)
	{
		Program &g = *g_program;
		for (const auto &pool : g.act_pools)
		{
			const uint32_t at = var<uint32_t>(Mem("arena_top"));
			var<uint32_t>(Mem(pool.first.c_str())) = at;
			var<uint32_t>(Mem("arena_top")) = at + pool.second;
		}
		for (const auto &pool : g.act_pools) fn<void (__cdecl *)(uint32_t, uint32_t)>(0x8DCC00)(var<uint32_t>(Mem(pool.first.c_str())), pool.second);
		for (const std::string &word : g.act_zero) var<uint16_t>(Mem(word.c_str())) = 0;
		if (g.act_stage_in >= 0) SpawnTask(g.act_stage_in, r);
#ifdef FXPROG_ACTORS
		for (const Program::ActCall &call : g.act_calls)
		{
			uint32_t a[3] = {};
			const size_t count = call.args.size() < 3 ? call.args.size() : 3;
			for (size_t i = 0; i < count; i++)
			{
				const std::string &arg = call.args[i];
				if (arg == "@caster") a[i] = (uint32_t)Entity(*((uint8_t *)r + 0x2C));   // (the root's caster slot)
				else a[i] = arg[0] == '@' ? Mem(arg.c_str() + 1) : (uint32_t)strtoul(arg.c_str(), nullptr, 0);
			}
			if (count == 0) ff8fx::act::callp(call.fn);
			else if (count == 1) ff8fx::act::callp(call.fn, a[0]);
			else if (count == 2) ff8fx::act::callp(call.fn, a[0], a[1]);
			else ff8fx::act::callp(call.fn, a[0], a[1], a[2]);
		}
#endif
	}

	inline void DirectorPhase(RootNode *r)
	{
#ifdef FXPROG_ACTORS
		if (!g_program->act_tail.empty() && r->h.phase >= 6)   // (the module's own master states from its state 6)
		{
			const size_t k = (size_t)(r->h.phase - 6);
			if (k < g_program->act_tail.size()) ff8fx::act::callp(g_program->act_tail[k], (uint32_t)r);
			return;
		}
#endif
		switch (r->h.phase)
		{
		case 0:
		case 1:
			r->h.phase++;
			break;
		case 2: // children gone (the act family's: its actor pools, the stage fade in)
			if (r->h.children == 0)
			{
				if (!g_program->act_pools.empty() || g_program->act_stage_in >= 0) ActPools(r);
				r->h.phase++;
			}
			break;
		case 3: // the spawned task of the current action
			r->busy = 1;
			SpawnTask(g_program->director_spawns, r);
			r->h.phase++;
			break;
		case 4: // when it is over, the next action (back to 3) or on
			if (r->busy == 0)
			{
				const int8_t a = r->h.action, t = r->h.target;
				if (g_program->per_target ? (int32_t)t < (int32_t)r->target_count - 1 : (int16_t)a < r->last_action)
				{
					if (g_program->per_target) r->h.target = (int8_t)(t + 1);   // (the next target record)
					else r->h.action = (int8_t)(a + 1);
					r->h.line++;
					r->h.phase--;
				}
				else
				{
					if (g_program->act_stage_out >= 0) ActCountdown(r) = (int16_t)V(g_program->act_wait);
					r->h.phase++;
				}
			}
			break;
		case 5: // (the act family's: after its countdown, the stage fade out)
			if (g_program->act_stage_out >= 0)
			{
				if (--ActCountdown(r) > 0) break;
				SpawnTask(g_program->act_stage_out, r);
			}
			r->h.phase++;
			break;
		case 6: // every queue empty
			if (r->alive == 0) r->h.phase++;
			break;
		case 7: // (the file released when it asks: its request's completion byte +0x62)
			if (g_program->release_file) fn<void (__cdecl *)(uint32_t, uint32_t)>(0x508630)(var<uint32_t>(Mem("texture_file")), (uint32_t)r + 0x62);
			r->h.phase++;
			break;
		case 8:
			if (!g_program->release_file || *((uint8_t *)r + 0x62) != 0) r->h.phase++;
			break;
		case 9: // done
			*(uint8_t *)&r->h.flags |= 1;
			r->h.phase++;
			break;
		default: break;
		}
	}

	inline void PoolBefore(const Pool &pool);

	// the short form (Double 0x8D5180): 0 on, 1 the current action's task (busy), 2 when it is over the
	// next action (back to 1) or on, 3 every queue empty: done; the arenas are memory words (arena_a
	// on odd ticks)
	inline uint32_t ShortDirector(TaskNode *n)
	{
		RootNode *r = (RootNode *)n;
		PacketCursor() = var<uint32_t>(Mem((r->tick & 1) ? "arena_a" : "arena_b"));
		UpdateTargetPosFromBones(r);
		switch (r->h.phase)
		{
		case 0: r->h.phase++; break;
		case 1:
			r->busy = 1;
			SpawnTask(g_program->director_spawns, r);
			r->h.phase++;
			break;
		case 2:
			if (r->busy == 0)
			{
				const int8_t a = r->h.action;
				if ((int16_t)a < r->last_action)
				{
					r->h.action = (int8_t)(a + 1);
					r->h.phase--;
				}
				else r->h.phase++;
			}
			break;
		case 3:
			if (r->alive == 0)
			{
				*(uint8_t *)&r->h.flags |= 1;
				r->h.phase++;
			}
			break;
		default: break;
		}
		r->alive = 0;
		for (const Pool &pool : g_program->pools)
		{
			if (pool.before) PoolBefore(pool);
			if (pool.tag >= 0) FX_PART(pool.tag);
			r->alive = (int16_t)(r->alive + ExecuteTaskQueue((TaskQueue *)pool.queue));
			if (pool.tag >= 0) FX_PART(0);
		}
		r->tick++;
		r->h.counter++;
		return EndWhenDone(&r->h);
	}

	// a pool's call before its queue runs: the module's function with its arguments (Stare's view-axis matrix
	// between its third and fourth queues)
	inline void PoolBefore(const Pool &pool)
	{
#ifdef FXPROG_ACTORS
		uint32_t a[3] = {};
		const size_t count = pool.before_args.size() < 3 ? pool.before_args.size() : 3;
		for (size_t i = 0; i < count; i++)
		{
			const std::string &arg = pool.before_args[i];
			a[i] = arg[0] == '@' ? Mem(arg.c_str() + 1) : (uint32_t)strtoul(arg.c_str(), nullptr, 0);
		}
		UseModule();
		if (count == 0) ff8fx::act::callp(pool.before);
		else if (count == 1) ff8fx::act::callp(pool.before, a[0]);
		else if (count == 2) ff8fx::act::callp(pool.before, a[0], a[1]);
		else ff8fx::act::callp(pool.before, a[0], a[1], a[2]);
#else
		(void)pool;
#endif
	}

	inline uint32_t PerActionDirector(TaskNode *n)
	{
		UseModule();
		if (g_program->director_short) return ShortDirector(n);
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
		for (const std::string &word : g_program->act_clear) var<uint16_t>(Mem(word.c_str())) = 0;
		for (const Pool &pool : g_program->pools)
		{
			if (pool.before) PoolBefore(pool);
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
	inline void MasterEvents(const std::vector<Step> &events, const MasterNode *m)
	{
		for (const Step &e : events)
		{
			if (e.op == SOUND_AT && m->counter == V(e.a[0]))   // tick, sound, pan
				BdPlaySE((const void *)fxp::sound((uint32_t)V(e.a[1]), (uint32_t)G(e.a[1])), 0, V(e.a[2]));
			if (e.op == FLASH_LEVEL_CLEAR) var<int32_t>(Mem("flash_level")) = 0;   // every tick (Blind: before its tasks raise it)
			if (e.op == SCREEN_FLASH_LEVEL) SetScreenFlash((uint32_t)var<int32_t>(Mem("flash_level")), 0);   // every tick, after them
		}
	}

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
			const std::vector<Val> &a = g.director_place.a;
			if (g.director_place.op == ACTION_TARGETS && t.field[F_LAYOUT] >= 0) DecodeLayout(t, s, (uint32_t)V(a[0]));
			if (g.director_place.op == TARGET_ANCHOR) // kind, bone, times a, share a, times b, share b, layout: on target 0 of action 0
			{
				layouts::AnchorPoint(Entity(Ctx()->actions[0].targets[0]), V(a[0]), V(a[1]), V(a[2]), V(a[3]), V(a[4]), V(a[5]),
				                     Fld<int16_t>(t, s, F_ANCHOR));
				DecodeLayout(t, s, (uint32_t)V(a[6]));
			}
		}
		if (m->started)
		{
			bool alive = false;
			if (g.camera_matrix) EffectCameraMatrix(&Camera(), &var<Mat4x3>(Mem("camera_matrix")));
			MasterEvents(g.director_events_first, m);
			for (const Pool &pool : g.pools)
			{
				if (pool.tag >= 0) FX_PART(pool.tag);
				if (ExecuteTaskQueue((TaskQueue *)pool.queue)) alive = true;
				if (pool.tag >= 0) FX_PART(0);
			}
			FX_PART(0);
			MasterEvents(g.director_events, m);
			if (!alive) return TASK_END;
		}
		m->counter++;
		return 0;
	}

	// one task per action, in turn (Silence 0x6BD980): at counter 1 of every n ticks the next
	// action's task (its action, target 0's entity marked, its layout); the node: counter, next
	// action (+0x0E), started, arena parity
	inline uint32_t CycleDirector(TaskNode *n)
	{
		Program &g = *g_program;
		MasterNode *m = (MasterNode *)n;
		// (arenas of its own memory: Reflect's, no magic buffer)
		const bool own_arenas = HasMem("packet_arena_a");
		if (m->arena)
		{
			PacketCursor() = own_arenas ? Mem("packet_arena_a") : MagicBuffer() + g.arena_a;
			m->arena = 0;
		}
		else
		{
			PacketCursor() = own_arenas ? Mem("packet_arena_b") : MagicBuffer() + g.arena_b;
			m->arena = 1;
		}
		MasterEvents(g.director_events_first, m);
		if (m->counter == g.director_spawn_tick)
		{
			if (!m->started)
			{
				m->started = 1;
				for (const Pool &pool : g.pools) InitTaskQueuePool((TaskQueue *)pool.queue, (void *)PoolStorage(pool), pool.size, pool.count);
			}
			uint8_t &action = m->pad0E;
			const std::vector<Val> &a = g.director_place.a;
			// mark, layout, layout b (0: none), spawn bone, busy tick (-1: none), size word base, times (0: none), busy on any target
			if (action <= Ctx()->actions[0].last_action && g.director_place.op == ACTION_TARGET)
			{
				const Task &t = g.tasks[g.director_spawns];
				// not while a task of that kind at the busy tick or before runs on that target (Dispel: the cycle restarts)
				uint8_t *target = Entity(Ctx()->actions[action].targets[0]);
				uint32_t colour = *(const uint32_t *)(target + 0x28);   // (the node's colour field: an older task's own on that target)
				bool busy = false;
				if (V(a[4]) >= 0)
				{
					const Pool &pool = g.pools[t.pool];
					for (int k = 0; k < pool.count && !busy; k++)
					{
						uint8_t *node = (uint8_t *)PoolStorage(pool) + k * pool.size;
						const bool running = (*(const uint8_t *)&((TaskNode *)node)->flags & 1) && (V(a[7]) || *Fld<uint8_t *>(t, node, F_ENTITY) == target);
						busy = running && *Fld<int16_t>(t, node, F_COUNTER) <= V(a[4]);   // (on any target: Zombie's)
						if (running && !busy && t.field[F_COLOUR] >= 0) colour = *Fld<uint32_t>(t, node, F_COLOUR);
					}
				}
				// (the next action only once its task started: Dispel's, Blind's, Petrify Stare's one-node pool)
				if (busy) m->counter = 0;
				else if (TaskNode *s = (TaskNode *)SpawnTask(g.director_spawns, nullptr))
				{
					*Fld<int16_t>(t, s, F_ACTION) = (int16_t)(uint16_t)action;
					uint8_t *e = Entity(Ctx()->actions[action].targets[0]);
					*Fld<uint8_t *>(t, s, F_ENTITY) = e;
					if (uint32_t *saved = Fld<uint32_t>(t, s, F_COLOUR)) *saved = colour;
					e[0] |= (uint8_t)V(a[0]);
					e[1] |= (uint8_t)(V(a[0]) >> 8);
					if (int16_t *anchor = Fld<int16_t>(t, s, F_ANCHOR))
					{
						GetDefaultEffectPosition(e, anchor);
						if (V(a[6])) anchor[3] = (int16_t)((*(const int16_t *)(e + 0x26) + V(a[5])) * V(a[6]));   // its size word
					}
					if (int16_t *spawn = Fld<int16_t>(t, s, F_SPAWN)) layouts::GetEffectSpawnPosition(e, V(a[3]), 0, spawn);
					if (layouts::Barrier *b = Fld<layouts::Barrier>(t, s, F_BARRIER))   // (Reflect's: at the middle of its effect points 0xF0 / 0xF1)
					{
						int16_t c[4];
						layouts::EffectCentre(e, c);
						b->model.t[0] = c[0];
						b->model.t[1] = c[1];
						b->model.t[2] = c[2];
					}
					if (t.field[F_LAYOUT] >= 0) DecodeLayout(t, s, (uint32_t)V(a[1]));
					if (V(a[2])) DecodeLayoutB(t, s, (uint32_t)V(a[2]));
					action++;
				}
			}
		}
		if (g.camera_matrix) EffectCameraMatrix(&Camera(), &var<Mat4x3>(Mem("camera_matrix")));   // Haste, Slow: every tick
		bool alive = false;
		if (m->started)
		{
			for (const Pool &pool : g.pools)
			{
				if (pool.tag >= 0) FX_PART(pool.tag);
				if (ExecuteTaskQueue((TaskQueue *)pool.queue)) alive = true;
				if (pool.tag >= 0) FX_PART(0);
			}
			FX_PART(0);
		}
		MasterEvents(g.director_events, m);   // (started or not: Blind's screen flash)
		if (m->started && !alive) return TASK_END;
		m->counter++;
		if (m->counter >= V(g.director_every)) m->counter = 0;
		return 0;
	}

	// one director per action, each starting the next one's (Fire 0x62A610): the root, a node of 0x10
	// bytes (its counter at +0x0C), alternates two packet arenas by its counter's parity and runs the
	// queues; the effect ends when they are empty
	inline uint32_t ChainRoot(TaskNode *n)
	{
		uint16_t &counter = *(uint16_t *)(n + 1);
		PacketCursor() = Mem("packet_arena_b");
		if (!(counter & 1)) PacketCursor() = Mem("packet_arena_a");
		bool alive = false;
		for (const Pool &pool : g_program->pools)
		{
			if (pool.tag >= 0) FX_PART(pool.tag);
			if (ExecuteTaskQueue((TaskQueue *)pool.queue)) alive = true;
			if (pool.tag >= 0) FX_PART(0);
		}
		counter++;
		return alive ? 0 : TASK_END;
	}
	// the director of `action`: the several targets' one when it has more than one target, else the
	// lone target's (its slot)
	inline void SpawnChainDirector(int action)
	{
		const Program &g = *g_program;
		const ActionData *ad = &Ctx()->actions[action];
		const int k = ad->target_count > 1 ? g.director_spawns : g.director_single;
		const Task &t = g.tasks[k];
		TaskNode *d = (TaskNode *)SpawnTask(k, nullptr);
		*Fld<int16_t>(t, d, F_ACTION) = (int16_t)action;
		if (k == g.director_single && t.field[F_SLOT] >= 0) *Fld<int16_t>(t, d, F_SLOT) = (int16_t)(uint16_t)ad->targets[0];
	}

	inline uint32_t __cdecl DirectorTask(TaskNode *n)
	{
		if (g_program->director == PORT) // the port's root, its module current
		{
			UseModule();
			void *root = ff8fx::own::find(g_program->port_root);
			return root ? ((uint32_t (__cdecl *)(TaskNode *))root)(n) : TASK_END;
		}
		if (g_program->director == CHAIN) return ChainRoot(n);
		if (g_program->director == CYCLE) return CycleDirector(n);
		return g_program->director == MASTER ? MasterDirector(n) : PerActionDirector(n);
	}

	inline uint32_t __cdecl FileLoader()
	{
		Program &g = *g_program;
		if (g.director == PORT)
		{
			UseModule();
			void *loader = ff8fx::own::find(g.port_loader);
			return loader ? ((uint32_t (__cdecl *)())loader)() : 0;
		}
		if (g.texture_data) return 0;   // (Thunder's loader loads nothing: its setup uploads exe data)
		fxp::FileName name = {};
		if (g.texture_param >= 0) strncpy(name.name, g.params[g.texture_param].text.c_str(), sizeof(name.name) - 1);
		for (const Program::ExtraFile &f : g.files)   // (the ones the game loads before its texture)
			if (f.first) var<uint32_t>(Mem(f.memory.c_str())) = IO_GetFile_MAGIC((const char *)f.name);
		const uint32_t file = IO_GetFile_MAGIC(fxp::file(name, (const char *)g.texture_name));
		var<uint32_t>(Mem("texture_file")) = file;
		for (const Program::ExtraFile &f : g.files)
			if (!f.first) var<uint32_t>(Mem(f.memory.c_str())) = IO_GetFile_MAGIC((const char *)f.name);
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
		if (g.camera) PlayCameraAnimation((const void *)g.camera);   // (none: Antidote's)
		return root_queue;
	}

	// the cycle director's setup (Silence 0x6BD910): the magic buffer, the cast, the director's node;
	// unless the cast repeats (flags & 1), the camera and the texture upload
	inline TaskQueue *CycleSetup(CastContext *ctx)
	{
		Program &g = *g_program;
		if (HasMem("magic_buffer")) MagicBuffer() = layouts::MagicBuffer();   // (Reflect: none)
		Ctx() = ctx;
		TaskQueue *root_queue = (TaskQueue *)Mem("root_queue");
		InitTaskQueuePool(root_queue, (void *)Mem("root_pool"), sizeof(MasterNode), 1);
		TaskNode *m = AddTaskToQueue(root_queue, g.root ? g.root : g.director_fn ? g.director_fn : (uint32_t)DirectorTask);
		Memset32(m + 1, 0, 2);
		if (!(ctx->flags & 1))
		{
			if (g.camera) PlayCameraAnimation((const void *)g.camera);
			QueueTimUpload(g.texture_data ? g.texture_data : var<uint32_t>(Mem("texture_file")));
		}
		if (g.seed_shared_rand) layouts::SeedSharedRand(CrtRand());
		return root_queue;
	}

	// the chain's setup (Fire 0x6298A0): the cast, its attacker, every slot free, the root, the pools,
	// action 0's director; unless the cast repeats (flags & 1), the camera and the texture upload
	inline TaskQueue *ChainSetup(CastContext *ctx)
	{
		Program &g = *g_program;
		Ctx() = ctx;
		if (HasMem("attacker_slot")) var<uint32_t>(Mem("attacker_slot")) = ctx->attacker;
		if (HasMem("target_free")) for (int k = 0; k < 7; k++) TargetFree()[k] = 1;
		TaskQueue *root_queue = (TaskQueue *)Mem("root_queue");
		InitTaskQueuePool(root_queue, (void *)Mem("root_pool"), 0x10, 1);
		TaskNode *r = AddTaskToQueue(root_queue, g.root ? g.root : g.director_fn ? g.director_fn : (uint32_t)DirectorTask);
		*(uint16_t *)(r + 1) = 0;
		for (const Pool &pool : g.pools) InitTaskQueuePool((TaskQueue *)pool.queue, (void *)PoolStorage(pool), pool.size, pool.count);
		SpawnChainDirector(0);
		if (!(ctx->flags & 1))
		{
			if (g.camera) PlayCameraAnimation((const void *)g.camera);
			QueueTimUpload(var<uint32_t>(Mem("texture_file")));
		}
		return root_queue;
	}

	inline void ApplyPatches()
	{
		for (const Patch &p : g_program->patches)
			switch (p.type)
			{
			case VAR_I16: case VAR_U16: var<int16_t>(p.at) = (int16_t)V(p.value); break;
			case VAR_I32: var<int32_t>(p.at) = V(p.value); break;
			default: var<uint8_t>(p.at) = (uint8_t)V(p.value); break;
			}
	}

	// a port module's own parameters (its live values) from the program's of the same keys
	inline void SetModuleParams()
	{
#ifdef FF8_FX_LAB
		if (!g_program->module) return;
		const ff8fx::fxp::Module *m = ff8fx::fxp::find_params(g_program->module);
		if (!m) return;
		memcpy(m->params, m->defaults, m->size);
		for (const Param &p : g_program->params)
			for (int i = 0; i < m->field_count; i++)
			{
				const ff8fx::fxp::Field &f = m->fields[i];
				if (p.key != f.key) continue;
				uint8_t *at = (uint8_t *)m->params + f.offset;
				if (f.type == ff8fx::fxp::File) // its name (empty, "-": the game's)
				{
					memset(at, 0, (size_t)f.max + 1);
					if (p.text != "-") strncpy((char *)at, p.text.c_str(), (size_t)f.max);
					continue;
				}
				if (f.type == ff8fx::fxp::I16) *(int16_t *)at = (int16_t)p.value;
				else if (f.type == ff8fx::fxp::U8) *at = (uint8_t)p.value;
				else *(int32_t *)at = p.value;
			}
#endif
	}

	inline TaskQueue *__cdecl Setup(CastContext *ctx)
	{
		Program &g = *g_program;
		ApplyPatches();
		g_params_of = nullptr;   // (at each cast: the program's values as they are now)
		if (g.director == PORT)
		{
			UseModule();
			if (g.port_setup_exe) // the module's own setup, then its root (the original's task) re-pointed at the program's director
			{
				TaskQueue *q = fn<TaskQueue *(__cdecl *)(CastContext *)>(g.port_setup)(ctx);
				for (TaskNode *n = q ? q->head : nullptr; n; n = n->next)
					if ((uint32_t)n->func == g.port_root) n->func = (uint32_t (__cdecl *)(TaskNode *))ProgramTaskOf(g.port_root);
				return q;
			}
			void *setup = ff8fx::own::find(g.port_setup);
			return setup ? ((TaskQueue *(__cdecl *)(CastContext *))setup)(ctx) : nullptr;
		}
		UseModule();   // (a port module's parameters)
		if (g.director == CHAIN) return ChainSetup(ctx);
		if (g.director == MASTER) return MasterSetup(ctx);
		if (g.director == CYCLE) return g.master_setup ? MasterSetup(ctx) : CycleSetup(ctx);
		if (g.director_short)
		{
			// Double's (0x8D5080): the root of the first target's slot, the cast; the camera and the
			// texture unless the cast repeats; the arenas in the magic buffer; the pools
			const uint8_t slot = ctx->actions[0].targets[0];
			TaskQueue *root_queue = (TaskQueue *)Mem("root_queue");
			InitTaskQueuePool(root_queue, (void *)Mem("root_pool"), 0x64, 2);
			RootNode *r = (RootNode *)AddEffectTask(root_queue, g.root ? g.root : g.director_fn ? g.director_fn : (uint32_t)DirectorTask, 0x64, nullptr);
			r->h.ctx = ctx;
			r->h.slot = slot;
			r->target_count = ctx->actions[0].target_count;
			r->last_action = ctx->actions[0].last_action;
			if (g.short_upload_always) QueueTimUpload(var<uint32_t>(Mem("texture_file")));   // (Phoenix Down's: no camera, the texture always)
			else if (!(ctx->flags & 1))
			{
				if (g.camera) PlayCameraAnimation((const void *)g.camera);
				QueueTimUpload(var<uint32_t>(Mem("texture_file")));
			}
			const uint32_t buffer = layouts::MagicBuffer();
			var<uint32_t>(Mem("arena_a")) = buffer + g.arena_a;
			var<uint32_t>(Mem("arena_b")) = buffer + g.arena_b;
			for (const Pool &pool : g.pools) InitTaskQueuePool((TaskQueue *)pool.queue, (void *)pool.storage, pool.size, pool.count);
			return root_queue;
		}
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
			if (g.camera) PlayCameraAnimation((const void *)g.camera);
			QueueTimUpload(var<uint32_t>(Mem("texture_file")));
		}
		const uint32_t file = var<uint32_t>(Mem("texture_file"));
		var<uint32_t>(Mem("arena_a")) = file;
		var<uint32_t>(Mem("limit_a")) = file + g.arena_size;
		var<uint32_t>(Mem("arena_b")) = file + g.arena_size;
		var<uint32_t>(Mem("arena_top")) = file + 2 * g.arena_size;
		var<uint32_t>(Mem("limit_b")) = file + 2 * g.arena_size;
		for (const Pool &pool : g.pools) InitTaskQueuePool((TaskQueue *)pool.queue, (void *)pool.storage, pool.size, pool.count);
		return root_queue;
	}

	// ------------------------------------------------------------------
	// Loading
	// ------------------------------------------------------------------
	inline Program *g_parsing = nullptr;          // the program being parsed (its data for @key)
	inline std::string g_parse_error;

	inline Val ParseVal(const std::string &token)
	{
		Val v;
		if (!token.empty() && token[0] == '$') { v.param = true; v.v = atoi(token.c_str() + 1); }
		else if (token.size() > 1 && token[0] == '-' && token[1] == '$') { v.param = true; v.neg = true; v.v = atoi(token.c_str() + 2); }
		else if (!token.empty() && token[0] == '@')
		{
			auto it = g_parsing ? g_parsing->data.find(token.substr(1)) : std::map<std::string, uint32_t>::iterator();
			if (g_parsing && it != g_parsing->data.end()) v.v = (int32_t)it->second;
			else if (g_parse_error.empty()) g_parse_error = "no data " + token.substr(1);
		}
		else v.v = (int32_t)strtoll(token.c_str(), nullptr, 0);
		return v;
	}
	inline uint32_t ParseNumber(const std::string &token) { return (uint32_t)ParseVal(token).v; }

	// the bytes `hex` as a blob of the program's own data, 16-byte aligned: its address
	inline uint32_t AddBlob(Program &g, const std::string &name, size_t size)
	{
		g.blobs.emplace_back(size + 16, 0);
		const uint32_t at = ((uint32_t)g.blobs.back().data() + 15u) & ~15u;
		g.data[name] = at;
		return at;
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

	// the program's own memory: one zeroed block, each piece 16-byte aligned
	inline void Allocate(Program &g)
	{
		auto align = [](uint32_t n) { return (n + 15u) & ~15u; };
		if (g.module && g.module_own && g.module_block.empty())
		{
			g.module_block.assign(g.module_size + 16, 0);
			g.module_reloc = align((uint32_t)g.module_block.data()) - g.module_lo;
			auto move = [&](uint32_t &a) { if (a >= g.module_lo && a < g.module_lo + g.module_size) a += g.module_reloc; };
			for (auto &m : g.memory) move(m.second);
			for (Pool &pool : g.pools) { move(pool.queue); move(pool.storage); }
		}
		uint32_t total = 0;
		for (const auto &m : g.own) total += align(m.second);
		for (const Pool &pool : g.pools)
			total += (pool.own_queue ? align(sizeof(TaskQueue)) : 0) + (pool.own_storage ? align(pool.size * pool.count) : 0);
		if (!total) return;
		g.block.assign(total + 16, 0);
		uint32_t at = align((uint32_t)g.block.data());
		for (const auto &m : g.own)
		{
			g.memory[m.first] = at;
			at += align(m.second);
		}
		for (Pool &pool : g.pools)
		{
			if (pool.own_queue) { pool.queue = at; at += align(sizeof(TaskQueue)); }
			if (pool.own_storage) { pool.storage = at; at += align(pool.size * pool.count); }
		}
	}

	// the program `text` (Fujin/effectprogram.py writes it); "" when it parsed, else what is wrong
	inline std::string Parse(const std::string &text, Program &g)
	{
		std::string error;
		int number = 0;
		Task *task = nullptr;
		size_t at = 0;
		g_parsing = &g;
		g_parse_error.clear();
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
			else if (d == "data" && need(3))
			{
				const std::string &hex = w[2];
				if (hex.size() % 2) error = "line " + std::to_string(number) + ": data " + w[1] + " is not hex";
				else
				{
					uint8_t *out = (uint8_t *)AddBlob(g, w[1], hex.size() / 2);
					for (size_t i = 0; i < hex.size(); i += 2) out[i / 2] = (uint8_t)strtoul(hex.substr(i, 2).c_str(), nullptr, 16);
				}
			}
			else if (d == "data_actors" && need(5))
			{
				// key, header offset, the exe address the bytes come from, hex: an act family's actor data copied whole
				// (its definitions, models, sequences and the header of their 4 tables); its pointers (the tables',
				// each definition's 32 per-frame tables) moved to the copy, the header's "relocated" flag kept
				const std::string &hex = w[4];
				const uint32_t header = (uint32_t)strtoul(w[2].c_str(), nullptr, 0), from = (uint32_t)strtoul(w[3].c_str(), nullptr, 0);
				const uint32_t size = (uint32_t)hex.size() / 2;
				if (hex.size() % 2 || header + 0x104 > size) error = "line " + std::to_string(number) + ": data_actors " + w[1] + " is not actor data";
				else
				{
					uint8_t *out = (uint8_t *)AddBlob(g, w[1], size);
					for (size_t i = 0; i < hex.size(); i += 2) out[i / 2] = (uint8_t)strtoul(hex.substr(i, 2).c_str(), nullptr, 16);
					// (tables the game left all zero point into the exe's zero-filled data, after the module's globals:
					// a zero block of its own instead)
					const uint32_t zeros = AddBlob(g, w[1] + ".zeros", 0x400);
					auto move = [&](uint32_t &p)
					{
						if (p >= from && p < from + size) p = p - from + (uint32_t)out;
						else if (p >= 0x188C000 && p < 0x279F000) p = zeros;
					};
					uint32_t *tables = (uint32_t *)(out + header + 4);
					for (int k = 0; k < 64; k++) move(tables[k]);
					for (int k = 0; k < 16; k++)
						if (tables[k]) for (int j = 0; j < 32; j++) move(((uint32_t *)(tables[k] + 0xC8))[j]);
					g.data[w[1]] = (uint32_t)out + header;
				}
			}
			else if (d == "patch" && need(5))
			{
				Patch p;
				p.at = ParseNumber(w[1]) + (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
				p.type = w[3] == "i16" ? VAR_I16 : w[3] == "u16" ? VAR_U16 : w[3] == "i32" ? VAR_I32 : VAR_U8;
				p.value = ParseVal(w[4]);
				g.patches.push_back(p);
			}
			else if (d == "arena_size" && need(2)) g.arena_size = (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
			else if (d == "per_target") g.per_target = true;
			else if (d == "port" && need(4))
			{
				g.port_setup = (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
				g.port_loader = (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
				g.port_root = (uint32_t)strtoul(w[3].c_str(), nullptr, 0);
				g.port_setup_exe = w.size() > 4 && w[4] == "exe";
			}
			else if (d == "release_file") g.release_file = true;
			else if (d == "module" && need(4))
			{
				g.module = atoi(w[1].c_str());
				g.module_lo = (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
				g.module_size = (uint32_t)strtoul(w[3].c_str(), nullptr, 0);
				g.module_own = w.size() > 4 && w[4] == "own";
			}
			else if (d == "module_pointer" && need(3)) g.module_pointers.push_back({ atoi(w[1].c_str()), (uint32_t)strtoul(w[2].c_str(), nullptr, 0) });
			else if (d == "code" && task && need(2)) task->code = (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
			else if (d == "native" && task && need(2)) task->native = (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
			else if (d == "act_stage" && need(4))
			{
				g.act_stage_in = atoi(w[1].c_str());
				g.act_stage_out = atoi(w[2].c_str());
				g.act_wait = ParseVal(w[3]);
			}
			else if (d == "act_pool" && need(3)) g.act_pools.push_back({ w[1], (uint32_t)strtoul(w[2].c_str(), nullptr, 0) });
			else if (d == "act_tail" && need(2))
				for (size_t k = 1; k < w.size(); k++) g.act_tail.push_back((uint32_t)strtoul(w[k].c_str(), nullptr, 0));
			else if (d == "act_call" && need(2))
				g.act_calls.push_back({ (uint32_t)strtoul(w[1].c_str(), nullptr, 0), std::vector<std::string>(w.begin() + 2, w.end()) });
			else if (d == "act_zero" && need(2)) g.act_zero.push_back(w[1]);
			else if (d == "act_clear" && need(2)) g.act_clear.push_back(w[1]);
			else if (d == "act_parts" && need(3))
			{
				g.act_part = atoi(w[1].c_str());
				g.act_first_part = atoi(w[2].c_str());
			}
			else if (d == "data_pointers" && need(3))
			{
				uint32_t *out = (uint32_t *)AddBlob(g, w[1], 4 * (w.size() - 2));
				for (size_t k = 2; k < w.size(); k++) out[k - 2] = ParseNumber("@" + w[k]);
			}
			else if (d == "function" && need(3))
			{
				const uint32_t at = (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
				if (w[1] == "file_loader") g.file_loader = at;
				else if (w[1] == "setup") g.setup = at;
				else if (w[1] == "root") g.root = at;
			}
			else if (d == "memory" && need(3)) g.memory[w[1]] = (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
			else if (d == "texture" && need(3)) { g.texture_name = ParseNumber(w[1]); g.texture_param = atoi(w[2].c_str()); }
			else if (d == "camera" && need(2)) g.camera = ParseNumber(w[1]);
			else if (d == "texture_data" && need(2)) g.texture_data = ParseNumber(w[1]);
			else if (d == "load_file" && need(3)) g.files.push_back({ w[1], ParseNumber(w[2]), w.size() > 3 && w[3] == "first" });
			else if (d == "own" && need(3)) g.own.push_back({ w[1], (uint32_t)strtoul(w[2].c_str(), nullptr, 0) });
			else if (d == "pool" && need(6))
			{
				Pool pool;
				pool.own_queue = w[1] == "own";
				pool.own_storage = w[2] == "own";
				pool.queue = pool.own_queue ? 0 : (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
				pool.storage = pool.own_storage ? 0 : (uint32_t)strtoul(w[2].c_str(), nullptr, 0);
				pool.size = atoi(w[3].c_str());
				pool.count = atoi(w[4].c_str());
				pool.tag = atoi(w[5].c_str());
				pool.base = w.size() > 6 ? atoi(w[6].c_str()) : 0;
				g.pools.push_back(pool);
			}
			else if (d == "pool_before" && need(2) && !g.pools.empty())
			{
				g.pools.back().before = (uint32_t)strtoul(w[1].c_str(), nullptr, 0);
				g.pools.back().before_args.assign(w.begin() + 2, w.end());
			}
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
				else if (w[1] == "chain" && need(4))
				{
					g.director = CHAIN;
					g.director_single = atoi(w[3].c_str());
				}
				else if (w[1] == "cycle" && need(5))
				{
					g.director = CYCLE;
					g.director_every = ParseVal(w[3]);
					g.director_place = ParseStep(w, 4, &error);
				}
				else if (w[1] == "port") g.director = PORT;
				else if (w[1] == "per_action")
				{
					g.director_short = w.size() > 3 && w[3] == "short";
					g.short_upload_always = w.size() > 4 && w[4] == "upload_always";
				}
				else error = "line " + std::to_string(number) + ": unknown director " + w[1];
			}
			else if (d == "director_event") g.director_events.push_back(ParseStep(w, 1, &error));
			else if (d == "director_event_first") g.director_events_first.push_back(ParseStep(w, 1, &error));
			else if (d == "camera_matrix") g.camera_matrix = true;
			else if (d == "master_setup") g.master_setup = true;
			else if (d == "seed_shared_rand") g.seed_shared_rand = true;
			else if (d == "cycle_spawn_tick" && need(2)) g.director_spawn_tick = atoi(w[1].c_str());
			else if (d == "param" && need(5))
			{
				Param p;
				p.key = w[1];
				p.type = w[2];
				if (p.type == "file") p.text = w[3] == "-" ? "" : w[3];
				else
				{
					p.value = as_type(p.type, ParseVal(w[3]).v);
					p.game = as_type(p.type, ParseVal(w[4]).v);
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
					if (f == F_LAYOUT_B) task->layout_b_size = atoi(w[3].c_str());
				}
			}
			else if (d == "order" && need(2)) task->draws_first = w[1] == "draws_first";
			else if (d == "draw_only" && need(2)) task->draw_only = w[1] == "skip" ? DRAW_ONLY_SKIP : w[1] == "after_draws" ? DRAW_ONLY_DRAWS : NO_DRAW_ONLY;
			else if (d == "hold") task->hold = ParseStep(w, 1, &error);
			else if (d == "move") task->moves.push_back(ParseStep(w, 1, &error));
			else if (d == "spawn_init" && !task->spawns.empty()) task->spawns.back().init.push_back(ParseStep(w, 1, &error));
			else if (d == "spawn_gate" && need(2) && !task->spawns.empty()) task->spawns.back().gate = atoi(w[1].c_str());
			else if (d == "draw_when" && !task->draws.empty()) task->draws.back().when = ParseStep(w, 1, &error);
			else if (d == "end") task->end = ParseStep(w, 1, &error);
			else if (d == "at_end") task->at_end.push_back(ParseStep(w, 1, &error));
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
			else if (d == "after") task->after.push_back(ParseStep(w, 1, &error));
			else if (d == "draw" && need(6))
			{
				Draw dr;
				dr.tag = atoi(w[1].c_str());
				dr.gate = atoi(w[2].c_str());
				dr.limit = w[3] == "below" ? BELOW : w[3] == "at_most" ? AT_MOST : w[3] == "at_least" ? AT_LEAST : w[3] == "within" ? WITHIN : NO_LIMIT;
				if (dr.limit != NO_LIMIT) dr.value = ParseVal(w[4]);
				if (dr.limit == WITHIN && need(7)) dr.count = ParseVal(w[5]);   // within from count (the draw after both)
				dr.draw = ParseStep(w, dr.limit == WITHIN ? 6 : 5, &error);
				task->draws.push_back(dr);
			}
			else if (error.empty()) error = "line " + std::to_string(number) + ": unknown " + d;
		}
		if (error.empty() && (int)g.tasks.size() > (int)(sizeof(THUNKS) / sizeof(THUNKS[0]))) error = "too many tasks";
		if (error.empty() && g.director != PORT && (g.director_spawns < 0 || g.director_spawns >= (int)g.tasks.size())) error = "the director spawns no task";
		if (error.empty() && g.director == CHAIN && (g.director_single < 0 || g.director_single >= (int)g.tasks.size())) error = "the chain has no lone target's director";
		if (error.empty() && !g_parse_error.empty()) error = g_parse_error;
		g_parsing = nullptr;
		if (error.empty()) Allocate(g);
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
