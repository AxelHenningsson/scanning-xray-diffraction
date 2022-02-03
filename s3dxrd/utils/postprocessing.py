import numpy as np
import vtkmodules.vtkIOXML as vtk_xml
import vtkmodules.util.numpy_support as vtk_np
from numpy import ndarray
from skimage import measure
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from numba import jit


def vtk_to_numpy(vtkfile, plot=False):
    """
    Import point cloud data stored in a VTK file to a list of Numpy arrays.

    :param plot: Plot the reconstructed data as a point cloud.
    :type plot: bool
    :param vtkfile: The path of the file containing the original data as an unstructured grid.
    :type vtkfile: str
    :return: Numpy array containing the data provided in the input file.
    :rtype: tuple[list[ndarray], ndarray]
    """
    fig = plt.figure()
    ax = plt.axes(projection='3d')

    filereader = vtk_xml.vtkXMLUnstructuredGridReader()
    filereader.SetFileName(vtkfile)
    filereader.Update()

    data = filereader.GetOutput()
    components = ["XX", "YY", "ZZ", "YZ", "XZ", "XY"]
    coords = vtk_np.vtk_to_numpy(data.GetPoints().GetData())
    values = [vtk_np.vtk_to_numpy(data.GetPointData().GetArray(comp)) for comp in components]
    if plot:
        xcoords = [arr[0] for arr in coords]
        ycoords = [arr[1] for arr in coords]
        zcoords = [arr[2] for arr in coords]

        ax.scatter(xcoords, ycoords, zcoords)
        plt.show()

    return values, coords


def alphashape(coords, nlayers=1, plot=False):
    # TODO: Implement multi-layer alpha shape calculation.
    """
    Calculate the alpha shape (the concave hull) for a point cloud consisting of a given set of
    three-dimensional coordinates. The code presumes that the coordinates are given in microns and that the
    measurements are taken 25 microns apart.

    :param coords: List of coordinates in x, y and z for the different points of the point cloud.
    :type coords:  list[ndarray]
    :param nlayers: Number of layers in the alpha shape, Defaults to one (the outermost layer).
    :type nlayers: int
    :param plot: Toggle plotting of the alpha shape as a point cloud and as a tessellated mesh body. Defaults to False.
    :type plot: bool
    :return: The coordinates of the points in the point cloud corresponding to the alpha shape.
    :rtype: list[ndarray]
    """
    coords_4d = np.hstack((coords, np.ones((coords.shape[0], 1))))

    transform_scale = np.array([[25., 0, 0, 0], [0, 25., 0, 0], [0, 0, 25., 0], [0, 0, 0, 1.]])
    inv_transform_scale = np.array([[1 / 25., 0, 0, 0], [0, 1 / 25., 0, 0], [0, 0, 1 / 25., 0], [0, 0, 0, 1.]])
    voxel_coords = (inv_transform_scale @ coords_4d.T)

    max_vals = np.amax(voxel_coords[:3, :], axis=1)
    min_vals = np.amin(voxel_coords[:3, :], axis=1)
    shift = np.array(_min_absolute_value(max_vals, min_vals))
    transform_direction = np.array([[1., 0, 0, -shift[0]], [0, 1., 0, -shift[1]], [0, 0, 1., -shift[2]], [0, 0, 0, 1.]])
    inv_transform_direction = np.array([[1., 0, 0, shift[0]], [0, 1., 0, shift[1]],
                                        [0, 0, 1., shift[2]], [0, 0, 0, 1.]])
    voxel_coords = transform_direction @ voxel_coords

    voxel_volume_size = np.around(max_vals - min_vals).astype(int)
    voxels = np.zeros((voxel_volume_size + np.ones_like(voxel_volume_size)))

    voxel_coords = np.around(voxel_coords[:3, :].T).astype(int)
    for x, y, z in voxel_coords:
        voxels[x, y, z] = 1

    # for i in range(np.shape(voxels)[2]):
    #     voxels[i] = ndimage.binary_fill_holes(voxels[i]).astype(int)
    # voxels = ndimage.binary_closing(voxels)
    voxels = np.pad(voxels, 1, constant_values=0)

    verts, faces, normals, values = measure.marching_cubes(voxels, step_size=1)
    verts_4d = np.hstack((verts, np.ones((verts.shape[0], 1))))
    verts_coords = (transform_scale @ inv_transform_direction @ verts_4d.T)

    best_approximations = find_best_approximations(voxel_coords, verts, normals)
    approx_4d = np.hstack((best_approximations, np.ones((best_approximations.shape[0], 1))))
    approx_coords = (transform_scale @ inv_transform_direction @ approx_4d.T)

    """
    result = None
    for vertx in verts_coords.T:
        arr_bc = np.broadcast_to(vertx.T, np.shape(coords_4d))
        indx = np.argmin(np.linalg.norm((arr_bc[:, :3] - coords_4d[:, :3]), axis=1), axis=0)
        
        if result is None:
            result = np.array([coords[indx]])
        else:
            result = np.concatenate((result, np.array([coords[indx]])), axis=0)

        coords_4d[indx] = [np.inf, np.inf, np.inf, np.inf]
    """

    # result = [coords[np.argmin(np.abs(arr - coords))] for arr in verts_coords]
    # result = np.vsplit((verts_coords.T)[:, :3], np.shape(verts_coords)[1])

    if plot:
        xcoords = [arr[0] for arr in approx_coords.T]
        ycoords = [arr[1] for arr in approx_coords.T]
        zcoords = [arr[2] for arr in approx_coords.T]

        fig = plt.figure(1)
        ax = plt.axes(projection='3d')
        ax.scatter(xcoords, ycoords, zcoords)

        fig2 = plt.figure(2, figsize=(10, 10))
        ax2 = fig2.add_subplot(111, projection='3d')
        ax2.set_xlim(0, 24)
        ax2.set_ylim(0, 20)
        ax2.set_zlim(0, 32)

        mesh = Poly3DCollection(verts[faces])
        mesh.set_edgecolor('k')
        ax2.add_collection3d(mesh)

        plt.tight_layout()
        plt.show()
    # return result


def _min_absolute_value(a1, a2):
    stacked = np.vstack((a1, a2))
    indices = np.argmin(np.absolute(stacked), axis=0)
    return [int(stacked[indices[0], 0]), int(stacked[indices[1], 1]), int(stacked[indices[2], 2])]


# def _point_plane_dist(point, normal, vertex):
#   d = -normal[0] * vertex[0] - normal[1] * vertex[1] - normal[2] * vertex[2]
#  dist = (normal[0] * point[0] + normal[1] * point[1] + normal[2] * point[2] + d) / np.linalg.norm(normal)
# return dist


@jit
def find_best_approximations(coords, verts, normals):
    best_approximations = np.zeros_like(normals)

    for j, (vertex, normal) in enumerate(zip(verts, normals)):
        distances = np.zeros(np.shape(coords)[0])

        for ii, point in enumerate(coords):
            d = -normal[0] * vertex[0] - normal[1] * vertex[1] - normal[2] * vertex[2]
            distances[ii] = (normal[0] * point[0] + normal[1] * point[1] + normal[2] * point[2] + d) / np.linalg.norm(
                normal)

        #if np.any(distances) > 0:  # The first-hand choice should be points that are outside the boundary defined by the
            # planes
            #minind = np.argmin(np.where(distances > 0, distances, np.inf))
            #best_approximations[j] = coords[minind]
            #coords = np.delete
        #else:
        minind = np.argmin(np.absolute(distances))
        best_approximations[j] = coords[minind]
        coords[minind] = [np.inf, np.inf, np.inf]
    return best_approximations


vals, coords = vtk_to_numpy("/home/philip/Desktop/grain_stress_5.vtu")
alphashape(coords, plot=True)
