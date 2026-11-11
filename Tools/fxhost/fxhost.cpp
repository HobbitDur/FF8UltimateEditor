// FujinEffects.dll: the effects Fujin writes, in the game (docs/fujin-effect-description.md, step 6).
//
// Fujin compiles an effect's description, with the parameters edited in its part tabs, into a
// program (Fujin/effectprogram.py) and saves it as FujinEffects/effect_NNN.fxprog in the game folder
// (a folder of this DLL's own: FFNx reads none of it). This DLL runs them: for every effect id with a
// program, it points the game's dispatch slot (MagicList_TextureLoad 0xC81DB8 / MagicList_Logic
// 0xC81774, read by Magic_GetIDLoad 0x50AF20) at the program's file loader and setup, and the
// effect runs from the program alone (Tools/fxhost/fxprogram.h, on FFNx's parts library). An
// effect of the exe (Cure...) is then replaced by its program, so its parameters take effect; a
// free slot (224, 225, 346-400) becomes a new effect, cast by any kernel.bin entry that names it.
//
// FFNx coexists: it only rewrites a slot that still holds an original it has a port for, and its
// effect camera files wrap whatever setup a slot holds.
//
// Loading: Junction VIII's mod.xml <LoadLibrary>FujinEffects.dll</LoadLibrary> (the DLL at the
// mod's root). The programs are read with CreateFileW (Junction VIII redirects it to a mod
// folder's file) at the first effect the game dispatches: Junction VIII loads the mod's DLLs
// BEFORE it maps the mod folders' files (AppWrapper/Wrap.cs Run), so a read at load time finds
// none of them and the slots stay empty (the game then plays effect 0, Cure). DllMain only points
// Magic_GetIDLoad's first instruction at the reading (DispatchHook). Messages go to
// %LOCALAPPDATA%\FujinEffects.log. Fujin's recorder loads it too (host=, FujinEffects_Install)
// to check it records what the programs do.

#include <windows.h>
#include <stdio.h>
#include <array>
#include <utility>

#include "fxprogram.h"

namespace ff8fx
{
	// the shared prim-model player: the game's 0x701970 (FFNx's twin when FFNx replaces it)
	int prim::play(prim::Layout *l, prim::Callback cb, int arg, int paused)
	{
		return ((int (__cdecl *)(prim::Layout *, prim::Callback, int, int))0x701970)(l, cb, arg, paused);
	}
	void register_port(uint32_t, void *, const char *, int) {}
	void *lookup(uint32_t) { return nullptr; }   // (the programs' nodes hold the ports' thunks: call the task's own function)
#ifdef FF8_FX_LAB
	// (the ports built in for the programs' port pieces: no lab here to note their parts)
	void fx_part(int) {}
	void fx_note(const char *, int32_t) {}
	void fx_place(int, uint32_t, int, int, const int32_t *) {}
	void fx_view(const void *, int, int, int) {}
#endif
}

namespace
{
	const uint32_t LOGIC = 0xC81774, TEXTURE_LOAD = 0xC81DB8;
	// Magic_GetIDLoad: its first instruction, sub esp, 200h (6 bytes), runs after the reading
	const uint32_t DISPATCH = 0x50AF20, DISPATCH_RESUME = DISPATCH + 6;
	const uint8_t DISPATCH_ORIGINAL[6] = { 0x81, 0xEC, 0x00, 0x02, 0x00, 0x00 };
	const int SLOTS = 400;
	fxprog::Program *g_slots[SLOTS];

	void Log(const char *format, ...)
	{
		char path[MAX_PATH];
		if (!GetEnvironmentVariableA("LOCALAPPDATA", path, MAX_PATH)) return;
		strcat_s(path, "\\FujinEffects.log");
		FILE *f = nullptr;
		if (fopen_s(&f, path, "a") || !f) return;
		va_list args;
		va_start(args, format);
		vfprintf(f, format, args);
		va_end(args);
		fputc('\n', f);
		fclose(f);
	}

	// each slot's entry points: they select its program, then run the runtime's
	template<int S> uint32_t __cdecl FileLoaderAt()
	{
		fxprog::g_program = g_slots[S];
		return fxprog::FileLoader();
	}
	template<int S> ff8fx::TaskQueue *__cdecl SetupAt(ff8fx::magc::CastContext *ctx)
	{
		fxprog::g_program = g_slots[S];
		return fxprog::Setup(ctx);
	}
	// the director runs each tick before its tasks (they run from its queues): the tasks' shared
	// thunks then find its program
	template<int S> uint32_t __cdecl DirectorAt(ff8fx::TaskNode *n)
	{
		fxprog::g_program = g_slots[S];
		return fxprog::DirectorTask(n);
	}
	template<size_t... I> std::array<uint32_t, SLOTS> FileLoaders(std::index_sequence<I...>) { return { { (uint32_t)FileLoaderAt<I>... } }; }
	template<size_t... I> std::array<uint32_t, SLOTS> Setups(std::index_sequence<I...>) { return { { (uint32_t)SetupAt<I>... } }; }
	template<size_t... I> std::array<uint32_t, SLOTS> Directors(std::index_sequence<I...>) { return { { (uint32_t)DirectorAt<I>... } }; }
	const std::array<uint32_t, SLOTS> FILE_LOADERS = FileLoaders(std::make_index_sequence<SLOTS>());
	const std::array<uint32_t, SLOTS> SETUPS = Setups(std::make_index_sequence<SLOTS>());
	const std::array<uint32_t, SLOTS> DIRECTORS = Directors(std::make_index_sequence<SLOTS>());

	void WriteSlot(uint32_t table, int slot, uint32_t value)
	{
		uint32_t *at = (uint32_t *)(table + 4 * slot);
		DWORD old;
		VirtualProtect(at, 4, PAGE_READWRITE, &old);
		*at = value;
		VirtualProtect(at, 4, old, &old);
	}

	bool ReadFileW(const std::wstring &path, std::string &text)
	{
		HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
		if (h == INVALID_HANDLE_VALUE) return false;
		char block[4096];
		DWORD n = 0;
		while (::ReadFile(h, block, sizeof(block), &n, nullptr) && n) text.append(block, n);
		CloseHandle(h);
		return true;
	}

	// every program in `folder`\FujinEffects: its slot points at it; the number installed
	int Install(const std::wstring &folder)
	{
		int installed = 0;
		for (int slot = 0; slot < SLOTS; slot++)
		{
			wchar_t name[64];
			swprintf_s(name, L"\\FujinEffects\\effect_%03d.fxprog", slot + 1);
			std::string text;
			if (!ReadFileW(folder + name, text)) continue;
			fxprog::Program *program = new fxprog::Program();
			const std::string error = fxprog::Parse(text, *program);
			if (!error.empty() || program->effect != slot + 1)
			{
				Log("effect_%03d.fxprog: %s", slot + 1, error.empty() ? "it is the program of another effect" : error.c_str());
				fxprog::Release(*program);
				delete program;
				continue;
			}
			fxprog::Detach(*program);
			program->director_fn = DIRECTORS[slot];
			if (g_slots[slot]) fxprog::Release(*g_slots[slot]);
			delete g_slots[slot];
			g_slots[slot] = program;
			WriteSlot(TEXTURE_LOAD, slot, FILE_LOADERS[slot]);
			WriteSlot(LOGIC, slot, SETUPS[slot]);
			Log("effect %d: %s, %d tasks, %d parameters", slot + 1, program->name.c_str(), (int)program->tasks.size(),
			    (int)program->params.size());
			installed++;
		}
		return installed;
	}

	// the game folder's programs, once (the game's thread, at its first effect)
	void __cdecl InstallOnce()
	{
		static bool done = false;
		if (done) return;
		done = true;
		wchar_t exe[MAX_PATH];
		GetModuleFileNameW(nullptr, exe, MAX_PATH);
		std::wstring folder = exe;
		folder.resize(folder.find_last_of(L"\\/"));
		Log("%d programs in %ls\\FujinEffects", Install(folder), folder.c_str());
	}

	uint32_t g_dispatch_resume = DISPATCH_RESUME;
	__declspec(naked) void DispatchHook()
	{
		__asm
		{
			call InstallOnce
			sub esp, 200h
			jmp g_dispatch_resume
		}
	}

	// Magic_GetIDLoad's first instruction jumps to DispatchHook; false when it is not the original
	bool HookDispatch()
	{
		uint8_t *at = (uint8_t *)DISPATCH;
		MEMORY_BASIC_INFORMATION info;   // (another process than the game: nothing there)
		if (!VirtualQuery(at, &info, sizeof(info)) || info.State != MEM_COMMIT || !(info.Protect & (PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE)))
			return false;
		if (memcmp(at, DISPATCH_ORIGINAL, sizeof(DISPATCH_ORIGINAL)) != 0) return false;
		DWORD old;
		if (!VirtualProtect(at, 6, PAGE_EXECUTE_READWRITE, &old)) return false;
		at[0] = 0xE9;
		*(uint32_t *)(at + 1) = (uint32_t)DispatchHook - (DISPATCH + 5);
		at[5] = 0x90;
		VirtualProtect(at, 6, old, &old);
		FlushInstructionCache(GetCurrentProcess(), at, 6);
		return true;
	}
}

// the programs of `folder`\FujinEffects installed now (Fujin's recorder); the number installed
extern "C" __declspec(dllexport) int __cdecl FujinEffects_Install(const wchar_t *folder)
{
	return Install(folder);
}

// a program played on one fighter outside the magic dispatch (Cronos's OneShotReflect: Reflect breaking,
// called from ApplyActionResultToTarget 0x506690 instead of the bounce flash 0x26, while the bounced spell's
// effect runs): 1 when it started, 0 when there is no such program or it cannot play there (then the caller
// plays the game's flash). Only a "shatter" program plays this way (fxshatter.h: resident models, no file,
// no magic buffer, no camera); game thread only.
extern "C" __declspec(dllexport) int __cdecl FujinEffects_PlayOnEntity(int effect_id, void *entity)
{
	InstallOnce();   // (the programs install at the first effect the game dispatches: a bounce comes after one)
	if (effect_id < 1 || effect_id > SLOTS || !entity) return 0;
	fxprog::Program *program = g_slots[effect_id - 1];
	if (!program || program->director != fxprog::SHATTER) return 0;
	return fxprog::shatter::PlayOnEntity(*program, (uint8_t *)entity) ? 1 : 0;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID)
{
	if (reason != DLL_PROCESS_ATTACH) return TRUE;
	// in the game only: the recorder installs by itself
	wchar_t exe[MAX_PATH];
	GetModuleFileNameW(nullptr, exe, MAX_PATH);
	const wchar_t *base = wcsrchr(exe, L'\\');
	if (base && _wcsnicmp(base + 1, L"fxrecorder", 10) == 0) return TRUE;
	if (!HookDispatch()) Log("Magic_GetIDLoad (0x%X) is not the original: no effect installed", DISPATCH);
	return TRUE;
}
