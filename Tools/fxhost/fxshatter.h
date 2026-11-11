// fxshatter.h: the "shatter" director (Reflect breaking, OneShotReflect in Cronos): one of the battle's
// resident prim models (the hit-effect models 0-10 of the exe table 0xC81678; 8 = Reflect's green dome,
// 9 Shell's, 10 Protect's) shown whole on a fighter, then broken like glass: each of its polygons becomes
// a shard that flies out from the model's centre, spins about its own middle, falls and fades. An
// optional burst (another model flashed at the centre) can come with the break.
//
// It is drawn the way the game draws its Reflect / Shell / Protect bounce flash: each shard is one call
// of that flash's draw task 0x570650 (rotation Y / Z, position, scale, the fade counter: 0-1 fading in,
// 2-3 solid, 4-7 fading out) on a model of one polygon, made here from the exe model (its vertices
// moved about the polygon's middle) and swapped into the table's entry for that one call. So it uses
// only exe data and the battle's resident texture page: it loads no file, uploads no texture, uses no
// magic buffer and starts no camera, and it can play while a spell's effect runs.
//
// Two ways in:
// - FujinEffects_PlayOnEntity(effect, entity) (fxhost.cpp): a task in the battle's hit-effect queue
//   (0x209FAA8, ticked by the battle loop whatever the magic effect does, at 15 Hz under True30) plays
//   the shatter on that fighter. Several calls while one plays add fighters (up to SHATTER_MAX).
// - A cast of the effect through the magic dispatch (Fujin's preview, a kernel.bin entry naming it):
//   one shatter on each of the action's targets, ticked by the effect's own root queue.
//
// The parameters (the program's "param" lines, Fujin's part tabs) are read when a shatter starts.

#include <cmath>

namespace fxprog
{
	namespace shatter
	{
		const uint32_t HIT_QUEUE = 0x209FAA8;      // TASK_QUEUE_ANIM_SEQ_99_B0_B1_B4_A5: the hit-effect queue (0x24-byte nodes)
		const uint32_t FLASH_DRAW = 0x570650;      // the bounce flash's draw task (Reflect/Shell/Protect)
		const uint32_t MODEL_TABLE = 0xC81678;     // its models (0x571240 reads entry flash model + 8)
		const uint32_t ROTATION = 0x56CD50;        // BuildRotationMatrixFromAngles(s16 angles[3], matrix)
		const uint32_t DEFAULT_POSITION = 0x571400;// GetDefaultEffectPosition(entity, coord)
		const uint32_t PLAY_SE_3D = 0x5017A0;      // BdPlaySystemSE3D(sound, attributes, coord)
		const int SHATTER_MAX = 8, SHARDS_MAX = 64, MODELS = 11;
		const int SWAP = 8;                         // the table entry a shard's model stands in for (one draw call)

#pragma pack(push, 1)
		// the flash draw's node (0x570650 reads it; a TaskNode header then these)
		struct FlashNode
		{
			TaskNode h;          // +0x00
			int16_t counter;     // +0x0C fade: 0-1 in, 2-3 solid, 4-7 out
			int16_t model;       // +0x0E the table entry - 8
			int16_t x, y, z;     // +0x10
			int16_t pad16;
			int16_t rot_y, rot_z;// +0x18
			int16_t scale;       // +0x1C 4096 = the model's own size
			int16_t pad1E;
			uint32_t pad20;
		};
		struct Coord { int16_t x, y, z, shadow; };
#pragma pack(pop)
		static_assert(sizeof(FlashNode) == 0x24, "the hit-effect queue's nodes are 0x24 bytes");

		// ---------------------------------------------------------------- the models' polygons
		// a prim model (primmodel.py): +0 lists offset (8 + 8 x vertices), +4 vertex count, the vertices
		// (s16 x, y, z, pad), then 8 lists (u32 count, records): F3 F4 FT3 FT4 G3 G4 GT3 GT4; a record's
		// vertex index = the vertex's byte offset / 4 (vertex k: 2k), at +4
		const int KIND_SIZE[8] = { 12, 12, 20, 24, 20, 24, 28, 36 };
		const int KIND_CORNERS[8] = { 3, 4, 3, 4, 3, 4, 3, 4 };
		struct Shard { uint32_t at; int16_t cx, cy, cz; };   // its one-polygon model (in Pieces::blob), its middle
		struct Pieces { bool built = false; std::vector<uint8_t> blob; std::vector<Shard> shards; };
		inline Pieces g_pieces[MODELS];

		inline uint32_t TableEntry(int index) { return ((const uint32_t *)MODEL_TABLE)[index]; }

		// the model's polygons, each a model of its own about its middle (built once per model)
		inline const Pieces &PiecesOf(int model)
		{
			Pieces &p = g_pieces[model];
			if (p.built) return p;
			p.built = true;
			const uint8_t *m = (const uint8_t *)TableEntry(model);
			const uint32_t lists = *(const uint32_t *)m, count = *(const uint32_t *)(m + 4);
			if (!count || count > 4096 || lists != 8 + 8 * count) return p;
			const int16_t *vertices = (const int16_t *)(m + 8);
			const uint8_t *at = m + lists;
			for (int kind = 0; kind < 8; kind++)
			{
				const uint32_t n = *(const uint32_t *)at;
				at += 4;
				for (uint32_t r = 0; r < n && p.shards.size() < SHARDS_MAX; r++, at += KIND_SIZE[kind])
				{
					const int corners = KIND_CORNERS[kind];
					int16_t v[4][3];
					int32_t c[3] = {};
					for (int k = 0; k < corners; k++)
					{
						const uint16_t index = *(const uint16_t *)(at + 4 + 2 * k) / 2;
						for (int a = 0; a < 3; a++) c[a] += (v[k][a] = vertices[4 * (index < count ? index : 0) + a]);
					}
					for (int a = 0; a < 3; a++) c[a] /= corners;
					// its model: header, its corners about the middle, the 8 lists (only its kind's holds it)
					Shard s = { (uint32_t)p.blob.size(), (int16_t)c[0], (int16_t)c[1], (int16_t)c[2] };
					std::vector<uint8_t> one(8 + 8 * corners + 4 * 8 + KIND_SIZE[kind], 0);
					*(uint32_t *)&one[0] = 8 + 8 * corners;
					*(uint32_t *)&one[4] = corners;
					for (int k = 0; k < corners; k++)
						for (int a = 0; a < 3; a++) *(int16_t *)&one[8 + 8 * k + 2 * a] = (int16_t)(v[k][a] - c[a]);
					uint8_t *out = &one[8 + 8 * corners];
					for (int k = 0; k < 8; k++)
					{
						*(uint32_t *)out = k == kind ? 1 : 0;
						out += 4;
						if (k != kind) continue;
						memcpy(out, at, KIND_SIZE[kind]);
						for (int j = 0; j < corners; j++) *(uint16_t *)(out + 4 + 2 * j) = (uint16_t)(2 * j);
						out += KIND_SIZE[kind];
					}
					while (p.blob.size() % 4) p.blob.push_back(0);
					s.at = (uint32_t)p.blob.size();
					p.blob.insert(p.blob.end(), one.begin(), one.end());
					p.shards.push_back(s);
				}
			}
			return p;
		}

		// ---------------------------------------------------------------- a shatter
		struct Piece { int32_t x, y, z, vx, vy, vz; int16_t ry, rz, vry, vrz; };   // its offset from the centre (<< 4)
		struct Settings
		{
			int32_t model, scale, turn, whole_ticks, sound, break_sound;
			int32_t burst_model, burst_scale, burst_ticks;
			int32_t speed, speed_random, rise, gravity, spin, life, fade_after;
		};
		struct Run
		{
			bool live = false;
			int owner = 0;                 // 0: the cast's root queue, 1: the hit-effect queue
			uint8_t *entity = nullptr;
			Coord at = {};
			int16_t facing = 0;
			int32_t tick = 0;
			uint32_t seed = 0;
			Settings s = {};
			int shards = 0;
			Piece pieces[SHARDS_MAX] = {};
		};
		inline Run g_runs[SHATTER_MAX];
		inline TaskNode *g_hit_task = nullptr;     // the hit-effect queue's ticking node (nullptr: none)
		inline uint32_t g_starts = 0;

		inline int32_t Value(const Program &g, const char *key, int32_t fallback)
		{
			for (const Param &p : g.params)
				if (p.key == key) return p.value;
			return fallback;
		}
		inline int32_t Clamp(int32_t v, int32_t lo, int32_t hi) { return v < lo ? lo : v > hi ? hi : v; }
		inline Settings Read(const Program &g)
		{
			Settings s;
			s.model = Clamp(Value(g, "whole.model", 8), 0, MODELS - 1);
			s.scale = Clamp(Value(g, "whole.scale", 5120), 0, 32767);
			s.turn = Value(g, "whole.turn", 0);
			s.whole_ticks = Clamp(Value(g, "whole.ticks", 3), 0, 60);
			s.sound = Value(g, "timing.sound", 0x72);
			s.break_sound = Value(g, "timing.break_sound", -1);
			s.burst_model = Clamp(Value(g, "burst.model", 4), 0, MODELS - 1);
			s.burst_scale = Clamp(Value(g, "burst.scale", 1024), 0, 32767);
			s.burst_ticks = Clamp(Value(g, "burst.ticks", 0), 0, 60);
			s.speed = Clamp(Value(g, "pieces.speed", 20), 0, 2000);
			s.speed_random = Clamp(Value(g, "pieces.speed_random", 16), 0, 2000);
			s.rise = Clamp(Value(g, "pieces.rise", 12), -2000, 2000);
			s.gravity = Clamp(Value(g, "pieces.gravity", 4), -200, 200);
			s.spin = Clamp(Value(g, "pieces.spin", 160), 0, 4096);
			s.life = Clamp(Value(g, "pieces.life", 14), 1, 120);
			s.fade_after = Clamp(Value(g, "pieces.fade_after", 6), 0, 120);
			return s;
		}

		// its own numbers (the game's rand() untouched: battle RNG and recordings stay as they are)
		inline int32_t Next(Run &r, int32_t range)
		{
			r.seed = r.seed * 1103515245u + 12345u;
			return range > 0 ? (int32_t)((r.seed >> 16) % (uint32_t)range) : 0;
		}

		inline void Sound(int32_t id, Coord &at)
		{
			if (id >= 0) fn<void (__cdecl *)(uint32_t, uint32_t, Coord *)>(PLAY_SE_3D)((uint32_t)id, 0x8000, &at);
		}

		// one draw of the flash task: `model` a table entry, or (shard) a one-polygon model swapped into entry SWAP
		inline void Draw(int model, const void *shard, int32_t x, int32_t y, int32_t z, int16_t ry, int16_t rz, int32_t scale,
		                 int16_t counter)
		{
			FlashNode n = {};
			n.counter = counter;
			n.model = (int16_t)((shard ? SWAP : model) - 8);
			n.x = (int16_t)x;
			n.y = (int16_t)y;
			n.z = (int16_t)z;
			n.rot_y = ry;
			n.rot_z = rz;
			n.scale = (int16_t)Clamp(scale, 0, 32767);
			uint32_t *entry = (uint32_t *)MODEL_TABLE + SWAP, saved = *entry;
			DWORD old = 0;
			if (shard)
			{
				VirtualProtect(entry, 4, PAGE_READWRITE, &old);
				*entry = (uint32_t)shard;
			}
			fn<uint32_t (__cdecl *)(FlashNode *)>(FLASH_DRAW)(&n);
			if (shard)
			{
				*entry = saved;
				VirtualProtect(entry, 4, old, &old);
			}
		}

		// the break: each shard starts where it is in the whole model (its middle through the model's turn and
		// size), flies out from the centre (faster with speed_random), up by rise, spins
		inline void Break(Run &r)
		{
			const Settings &s = r.s;
			const Pieces &p = PiecesOf(s.model);
			int16_t angles[3] = { 0, (int16_t)(r.facing + s.turn), 0 };
			Mat4x3 m = {};
			fn<void (__cdecl *)(int16_t *, Mat4x3 *)>(ROTATION)(angles, &m);
			r.shards = (int)p.shards.size();
			for (int k = 0; k < r.shards; k++)
			{
				const Shard &sh = p.shards[k];
				Piece &q = r.pieces[k];
				int32_t w[3];
				for (int a = 0; a < 3; a++)
					w[a] = (int32_t)(((int64_t)m.m[a][0] * sh.cx + (int64_t)m.m[a][1] * sh.cy + (int64_t)m.m[a][2] * sh.cz) >> 12) * s.scale >> 12;
				q.x = w[0] << 4;
				q.y = w[1] << 4;
				q.z = w[2] << 4;
				const double length = sqrt((double)w[0] * w[0] + (double)w[1] * w[1] + (double)w[2] * w[2]);
				const int32_t v = s.speed + Next(r, s.speed_random + 1);
				for (int a = 0; a < 3; a++) (&q.vx)[a] = length > 0 ? (int32_t)(16.0 * v * w[a] / length) : 0;
				q.vy -= s.rise << 4;
				q.ry = 0;
				q.rz = 0;
				q.vry = (int16_t)(Next(r, 2 * s.spin + 1) - s.spin);
				q.vrz = (int16_t)(Next(r, 2 * s.spin + 1) - s.spin);
			}
		}

		// one tick of a shatter (draw_only: draw as it is, nothing moves); false once it is over
		inline bool Tick(Run &r, bool draw_only)
		{
			const Settings &s = r.s;
			const int16_t turn = (int16_t)(r.facing + s.turn);
			if (r.tick < s.whole_ticks)
				Draw(s.model, nullptr, r.at.x, r.at.y, r.at.z, turn, 0, s.scale, (int16_t)(r.tick == 0 && s.whole_ticks > 1 ? 1 : 2));
			else
			{
				const int32_t age = r.tick - s.whole_ticks;
				if (age >= (r.shards ? s.life : 0) && age >= s.burst_ticks) return false;   // (no shards: over with the burst)
				if (age < s.burst_ticks)   // the burst: solid, then fading out in 4 steps, growing
				{
					const int16_t c = (int16_t)(age == 0 ? 2 : 4 + Clamp((age - 1) * 4 / (s.burst_ticks > 1 ? s.burst_ticks - 1 : 1), 0, 3));
					Draw(s.burst_model, nullptr, r.at.x, r.at.y, r.at.z, turn, 0, s.burst_scale + age * s.burst_scale / 4, c);
				}
				if (age < s.life && r.shards)
				{
					int16_t counter = 2;
					if (age >= s.fade_after)
					{
						const int32_t span = s.life - s.fade_after;
						counter = (int16_t)(4 + Clamp((age - s.fade_after) * 4 / (span > 0 ? span : 1), 0, 3));
					}
					const Pieces &p = PiecesOf(s.model);
					for (int k = 0; k < r.shards; k++)
					{
						const Piece &q = r.pieces[k];
						Draw(s.model, &p.blob[p.shards[k].at], r.at.x + (q.x >> 4), r.at.y + (q.y >> 4), r.at.z + (q.z >> 4),
						     (int16_t)(turn + q.ry), q.rz, s.scale, counter);
					}
				}
			}
			if (draw_only) return true;
			r.tick++;
			if (r.tick == s.whole_ticks)
			{
				Break(r);
				Sound(s.break_sound, r.at);
			}
			else if (r.tick > s.whole_ticks)
				for (int k = 0; k < r.shards; k++)
				{
					Piece &q = r.pieces[k];
					q.x += q.vx;
					q.y += q.vy;
					q.z += q.vz;
					q.vy += s.gravity << 4;
					q.ry = (int16_t)(q.ry + q.vry);
					q.rz = (int16_t)(q.rz + q.vrz);
				}
			return true;
		}

		// a shatter on `entity` (a battle entity slot); false when every run is taken
		inline bool Start(const Program &g, uint8_t *entity, int owner)
		{
			for (Run &r : g_runs)
			{
				if (r.live) continue;
				r = Run();
				r.live = true;
				r.owner = owner;
				r.entity = entity;
				r.s = Read(g);
				fn<void (__cdecl *)(uint8_t *, Coord *)>(DEFAULT_POSITION)(entity, &r.at);
				r.facing = *(int16_t *)(entity + 0x0E);   // based_rotation_y (the bounce flash's turn)
				r.seed = 0x5EED0000u + (uint32_t)((entity - Entity(0)) / 0x9C) * 977u + g_starts++ * 7919u;
				Sound(r.s.sound, r.at);
				if (r.s.whole_ticks == 0)
				{
					Break(r);
					Sound(r.s.break_sound, r.at);
				}
				return true;
			}
			return false;
		}

		// every live run of this owner ticked; true while one plays
		inline bool TickAll(int owner)
		{
			const bool draw_only = (UpdateFlags() & 1) != 0;
			bool any = false;
			for (Run &r : g_runs)
				if (r.live && r.owner == owner)
				{
					if (Tick(r, draw_only)) any = true;
					else r.live = false;
				}
			return any;
		}

		// the hit-effect queue's task: 0 (on) while a shatter plays, 2 (end) after
		inline uint32_t __cdecl HitTask(TaskNode *)
		{
			if (TickAll(1)) return 0;
			g_hit_task = nullptr;
			return 2;
		}

		// our task still in the hit-effect queue (the battle re-inits the queue at its start: a task of
		// the last battle is gone, and its runs with it)
		inline bool HitTaskQueued()
		{
			if (!g_hit_task) return false;
			for (TaskNode *n = ((TaskQueue *)HIT_QUEUE)->head; n; n = n->next)
				if (n == g_hit_task) return (n->flags & 1) && n->func == HitTask;
			return false;
		}

		// FujinEffects_PlayOnEntity's work: true when it started (or joined) a shatter
		inline bool PlayOnEntity(const Program &g, uint8_t *entity)
		{
			if (!entity) return false;
			if (!HitTaskQueued())
			{
				g_hit_task = nullptr;
				for (Run &r : g_runs)
					if (r.owner == 1) r.live = false;
			}
			if (!Start(g, entity, 1)) return false;
			if (!g_hit_task) g_hit_task = AddTaskToQueue((TaskQueue *)HIT_QUEUE, (uint32_t)HitTask);
			return true;
		}

		// a cast through the magic dispatch: a shatter on each target, ticked by the root queue's task
		inline uint8_t g_cast_pool[0x40];
		inline TaskQueue g_cast_queue_header;
		inline uint32_t __cdecl CastTask(TaskNode *) { return TickAll(0) ? 0 : 2; }
		inline TaskQueue *CastSetup(const Program &g, CastContext *ctx)
		{
			for (Run &r : g_runs)
				if (r.owner == 0) r.live = false;   // (a new cast: the last one's leftovers go)
			const ActionData &a = ctx->actions[0];
			for (int k = 0; k < a.target_count; k++) Start(g, Entity(a.targets[TARGET_STRIDE * k]), 0);
			InitTaskQueuePool(&g_cast_queue_header, g_cast_pool, 0x20, 1);
			AddTaskToQueue(&g_cast_queue_header, (uint32_t)CastTask);
			return &g_cast_queue_header;
		}
	}
}
