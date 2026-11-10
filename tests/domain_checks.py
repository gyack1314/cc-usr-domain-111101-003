from datapack.domain import union_length,positive_overlap,validate_relation
def check(case):
    case.assertEqual(union_length([(0,10),(5,15),(15,20)]),20)
    case.assertFalse(positive_overlap((0,5),(5,10)))
    case.assertTrue(positive_overlap((0,6),(5,10)))
    case.assertEqual(validate_relation({'left':'a','right':'b','kind':'similar'},{'a'}),['right'])
    with case.assertRaises(ValueError):union_length([(10,0)])
