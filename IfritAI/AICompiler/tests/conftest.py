# conftest.py
import pytest
from lark import Lark

from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AICompiler import AICompiler


@pytest.fixture
def ai_compiler():
    """Create an AICompiler instance for testing"""
    game_data = GameData("..\\..\\..\\FF8GameData")
    game_data.load_all()
    return AICompiler(game_data)


@pytest.fixture
def parser(ai_compiler):
    """Create a Lark parser instance using the grammar from AICompiler"""
    return Lark(ai_compiler.grammar, start='start', parser='lalr')
    
@pytest.fixture    
def if_else_structure_data():
    source_code_raw = """
                        if(100, 200, 3, 99)
                        {
                            if(100, 200, 4, 2)
                            {
                                if(101, 200, 5, 4)
                                {
                                    die;
                                }
                            }
                            elseif(100, 200, 0, 10)
                            {
                                die;
                                if(101, 200, 5, 2)
                                {
                                    die;
                                }
                            }
                            elseif(100, 200, 0, 20)
                            {
                                die;
                                if(101, 200, 4, 5)
                                {
                                    die;
                                }
                                elseif(101, 200, 5, 6)
                                {
                                    die;
                                }
                            }
                            elseif(100, 200, 0, 30)
                            {
                                die;
                                if(101, 200, 4, 3)
                                {
                                    die;
                                }
                                elseif(101, 200, 5, 6)
                                {
                                    die;
                                }
                            }
                        }
                        else
                        {
                            die;
                            if(2, 3, 0, 0)
                            {
                                if(6, 202, 3, 1)
                                {
                                    if(1, 87, 2, 0)
                                    {
                                        if(9, 0, 3, 88)
                                        {
                                            if(227, 200, 1, 64)
                                            {
                                                if(6, 200, 2, 1)
                                                {
                                                    die;
                                                    if(6, 20, 0, 3)
                                                    {
                                                        die;
                                                        if(2, 3, 0, 0)
                                                        {
                                                            die;
                                                        }
                                                        elseif(2, 2, 0, 0)
                                                        {
                                                            die;
                                                        }
                                                    }
                                                    elseif(6, 200, 0, 2)
                                                    {
                                                        die;
                                                        if(2, 2, 0, 0)
                                                        {
                                                            die;
                                                        }
                                                    }
                                                }
                                            }
                                            elseif(227, 200, 1, 128)
                                            {
                                                die;
                                            }
                                            elseif(227, 200, 1, 192)
                                            {
                                                die;
                                            }
                                            else
                                            {
                                                die;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        """
    source_code_type = """
                        if(BattleVar100, !=, 99)
                        {
                            if(BattleVar100, <=, 2)
                            {
                                if(BattleVar101, >=, 4)
                                {
                                    die;
                                }
                            }
                            elseif(BattleVar100, ==, 10)
                            {
                                die;
                                if(BattleVar101, >=, 2)
                                {
                                    die;
                                }
                            }
                            elseif(BattleVar100, ==, 20)
                            {
                                die;
                                if(BattleVar101, <=, 5)
                                {
                                    die;
                                }
                                elseif(BattleVar101, >=, 6)
                                {
                                    die;
                                }
                            }
                            elseif(BattleVar100, ==, 30)
                            {
                                die;
                                if(BattleVar101, <=, 3)
                                {
                                    die;
                                }
                                elseif(BattleVar101, >=, 6)
                                {
                                    die;
                                }
                            }
                        }
                        else
                        {
                            die;
                            if(RANDOM, 3, ==, 0)
                            {
                                if(ALIVE_IN_TEAM, ALLY_TEAM, !=, 1)
                                {
                                    if(HP_IN_TEAM, G-Soldier, > 0%)
                                    {
                                        if(IS_ALIVE, !=, "Elite Soldier")
                                        {
                                            if(varH, Self, <, 64)
                                            {
                                                if(ALIVE_IN_TEAM, ENEMY_TEAM, >, 1)
                                                {
                                                    die;
                                                    if(ALIVE_IN_TEAM, ENEMY_TEAM, ==, 3)
                                                    {
                                                        die;
                                                        if(RANDOM, 3, ==, 0)
                                                        {
                                                            die;
                                                        }
                                                        elseif(RANDOM, 2, ==, 0)
                                                        {
                                                            die;
                                                        }
                                                    }
                                                    elseif(ALIVE_IN_TEAM, ENEMY_TEAM, ==, 2)
                                                    {
                                                        die;
                                                        if(RANDOM, 2, ==, 0)
                                                        {
                                                            die;
                                                        }
                                                    }
                                                }
                                            }
                                            elseif(varH, Self, <, 128)
                                            {
                                                die;
                                            }
                                            elseif(varH, Self, <, 192)
                                            {
                                                die;
                                            }
                                            else
                                            {
                                                die;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        """
    bytecode = [2, 100, 200, 3, 99, 0, 123, 0, 2, 100, 200, 4, 2, 0, 15, 0, 2, 101, 200, 5, 4, 0, 4, 0, 8, 35, 0,
            0, 35, 0, 0, 2, 100, 200, 0, 10, 0, 16, 0, 8, 2, 101, 200, 5, 2, 0, 4, 0, 8, 35, 0, 0, 35, 0, 0, 2, 100, 200, 0, 20, 0,
            28, 0, 8, 2, 101, 200, 4, 5, 0, 4, 0, 8, 35, 0, 0, 2, 101, 200, 5, 6, 0, 4, 0, 8, 35, 0, 0, 35, 0, 0, 2, 100,
            200, 0, 30, 0, 28, 0, 8, 2, 101, 200, 4, 3, 0, 4, 0, 8, 35, 0, 0, 2, 101, 200, 5, 6, 0, 4, 0, 8, 35, 0, 0, 35, 0,
            0, 35, 0, 0, 8, 2, 2, 3, 0, 0, 0, 144, 0, 2, 6, 201, 3, 1, 0, 136, 0, 2, 1, 87, 2, 0, 0, 128, 0, 2, 9, 0, 3, 88, 
            0, 120, 0, 2, 227, 200, 1, 64, 0, 75, 0, 2, 6, 200, 2, 1, 0, 64, 0, 8, 2, 6, 200, 0, 3, 0, 28, 0, 8, 2, 2, 3,
            0, 0, 0, 4, 0, 8, 35, 0, 0, 2, 2, 2, 0, 0, 0, 4, 0, 8, 35, 0, 0, 35, 0, 0, 2, 6, 200, 0, 2, 0, 16, 0, 8, 2, 2,
            2, 0, 0, 0, 4, 0, 8, 35, 0, 0, 35, 0, 0, 35, 0, 0, 35, 0, 0, 2, 227, 200, 1, 128, 0, 4, 0, 8, 35, 13, 0, 2, 227,
            200, 1, 192, 0, 4, 0, 8, 35, 1, 0, 8, 35, 0, 0, 35, 0, 0, 35, 0, 0, 35, 0, 0]
    data = { "source_code_type": source_code_type, "bytecode": bytecode }
    return data