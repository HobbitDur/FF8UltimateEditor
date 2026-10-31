// FujinEffects.dll: the effects Fujin writes, in the game (docs/fujin-effect-description.md, step 6).
//
// Fujin compiles an effect's description, with the parameters edited in its part tabs, into a
// program (Fujin/effectprogram.py) and saves it as direct/exe/effect_NNN.fxprog in the game folder
// (next to FFNx's effect_NNN.bcam camera files). This DLL runs them: for every effect id with a
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
// folder's file) on a thread of their own, after the loader lock: never inside DllMain. Messages go
// to %LOCALAPPDATA%\FujinEffects.log. Fujin's recorder loads it too (host=, FujinEffects_Install)
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
}

namespace
{
	const uint32_t LOGIC = 0xC81774, TEXTURE_LOAD = 0xC81DB8;
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

	// every program in `folder`\direct\exe: its slot points at it; the number installed
	int Install(const std::wstring &folder)
	{
		int installed = 0;
		for (int slot = 0; slot < SLOTS; slot++)
		{
			wchar_t name[64];
			swprintf_s(name, L"\\direct\\exe\\effect_%03d.fxprog", slot + 1);
			std::string text;
			if (!ReadFileW(folder + name, text)) continue;
			fxprog::Program *program = new fxprog::Program();
			const std::string error = fxprog::Parse(text, *program);
			if (!error.empty() || program->effect != slot + 1)
			{
				Log("effect_%03d.fxprog: %s", slot + 1, error.empty() ? "it is the program of another effect" : error.c_str());
				delete program;
				continue;
			}
			fxprog::Detach(*program);
			program->director_fn = DIRECTORS[slot];
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

	DWORD WINAPI InstallThread(void *)
	{
		wchar_t exe[MAX_PATH];
		GetModuleFileNameW(nullptr, exe, MAX_PATH);
		std::wstring folder = exe;
		folder.resize(folder.find_last_of(L"\\/"));
		Install(folder);
		return 0;
	}
}

// the programs of `folder`\direct\exe installed now (Fujin's recorder); the number installed
extern "C" __declspec(dllexport) int __cdecl FujinEffects_Install(const wchar_t *folder)
{
	return Install(folder);
}

BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID)
{
	if (reason != DLL_PROCESS_ATTACH) return TRUE;
	// in the game only: the recorder installs by itself
	wchar_t exe[MAX_PATH];
	GetModuleFileNameW(nullptr, exe, MAX_PATH);
	const wchar_t *base = wcsrchr(exe, L'\\');
	if (base && _wcsnicmp(base + 1, L"fxrecorder", 10) == 0) return TRUE;
	if (HANDLE thread = CreateThread(nullptr, 0, InstallThread, nullptr, 0, nullptr)) CloseHandle(thread);
	return TRUE;
}
